"""Download personal NYT Wordle play history for analysis.

This pulls *your own* saved Wordle games from the NYT and writes a tidy
per-day CSV. It combines two data sources:

  * The public per-date endpoint (no auth) -> the puzzle ``id`` and the
    day's ``solution``. NYT assigns puzzle ids from a non-chronological
    editorial pool, so the id cannot be computed from the date; we look it
    up and cache it in ``data/puzzle_index.json``.
  * The authenticated state endpoint -> your saved board and stats. This
    requires the ``NYT-S`` session cookie.

Getting the cookie (one-time): log in to the NYT in webctl, then extract
the cookie (see README). ``load_cookie`` checks, in order, the ``NYT_S``
environment variable, a gitignored ``.nyt_cookie`` file, and the cookie
saved in a webctl session profile.

Usage:
    python nyt_history.py extract-cookie          # pull NYT-S from webctl
    python nyt_history.py download                # full history -> CSV
    python nyt_history.py download --start 2024-01-01 --end 2024-01-07
"""

import argparse
import csv
import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
COOKIE_FILE = HERE / ".nyt_cookie"
INDEX_FILE = DATA_DIR / "puzzle_index.json"
OUTPUT_CSV = DATA_DIR / "wordle_personal_history.csv"
STATS_JSON = DATA_DIR / "wordle_stats.json"
WEBCTL_PROFILES = Path.home() / "Library" / "Application Support" / "webctl" / "profiles"

LAUNCH_DATE = dt.date(2021, 6, 19)
DATE_URL = "https://www.nytimes.com/svc/wordle/v2/{date}.json"
STATE_URL = "https://www.nytimes.com/svc/games/state/wordleV2/latests?puzzle_ids={ids}"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REFERER = "https://www.nytimes.com/games/wordle/index.html"


# --- cookie handling -------------------------------------------------------

def load_cookie():
    """Return the NYT-S cookie value, or raise if none can be found."""
    val = os.environ.get("NYT_S")
    if val:
        return val.strip()
    if COOKIE_FILE.exists():
        val = COOKIE_FILE.read_text().strip()
        if val:
            return val
    val = cookie_from_webctl()
    if val:
        return val
    raise SystemExit(
        "No NYT-S cookie found. Log in to the NYT with webctl, then run:\n"
        "    python nyt_history.py extract-cookie\n"
        "or set the NYT_S environment variable."
    )


def cookie_from_webctl(name="NYT-S"):
    """Scan saved webctl session profiles for the NYT-S cookie value.

    ``webctl save`` writes a Playwright-style storage-state JSON containing
    cookies (including HttpOnly ones like NYT-S). We pick the most recently
    modified profile file that has the cookie.
    """
    if not WEBCTL_PROFILES.exists():
        return None
    candidates = sorted(
        WEBCTL_PROFILES.rglob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        cookies = data.get("cookies") if isinstance(data, dict) else None
        if not cookies:
            continue
        for cookie in cookies:
            if cookie.get("name") == name and "nytimes.com" in cookie.get("domain", ""):
                return cookie.get("value")
    return None


def extract_cookie():
    """Find the NYT-S cookie in webctl and cache it to .nyt_cookie."""
    val = cookie_from_webctl()
    if not val:
        raise SystemExit(
            "Could not find an NYT-S cookie in webctl profiles at\n"
            f"    {WEBCTL_PROFILES}\n"
            "Log in first:  webctl navigate \"https://www.nytimes.com/account/login\"\n"
            "then:          webctl save \"nyt\""
        )
    COOKIE_FILE.write_text(val)
    print(f"Saved NYT-S cookie to {COOKIE_FILE}")


# --- HTTP ------------------------------------------------------------------

def get_json(url, cookie=None, retries=3, backoff=1.0):
    """GET a URL and parse JSON, retrying transient failures."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Referer": REFERER}
    if cookie:
        headers["Cookie"] = f"NYT-S={cookie}"
    req = urllib.request.Request(url, headers=headers)
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            # 4xx (auth/not-found) won't improve on retry; surface immediately.
            if e.code < 500:
                raise
            last_err = e
        except urllib.error.URLError as e:
            last_err = e
        time.sleep(backoff * (attempt + 1))
    raise last_err if last_err else RuntimeError(f"Failed to GET {url}")


# --- puzzle date -> id/solution index --------------------------------------

def date_range(start, end):
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)


def build_index(start, end, throttle=0.1):
    """Map each date in range to {"id", "solution"} via the public endpoint.

    Cached in INDEX_FILE; only missing dates are fetched.
    """
    DATA_DIR.mkdir(exist_ok=True)
    index = {}
    if INDEX_FILE.exists():
        index = json.loads(INDEX_FILE.read_text())
    changed = False
    for day in date_range(start, end):
        key = day.isoformat()
        if key in index:
            continue
        try:
            meta = get_json(DATE_URL.format(date=key))
        except urllib.error.HTTPError as e:
            print(f"  {key}: no puzzle ({e.code})")
            continue
        index[key] = {"id": meta["id"], "solution": meta.get("solution")}
        changed = True
        time.sleep(throttle)
    if changed:
        INDEX_FILE.write_text(json.dumps(index, indent=2, sort_keys=True))
    return index


# --- saved game state ------------------------------------------------------

def fetch_states(puzzle_ids, cookie, batch_size=31, throttle=0.3):
    """Fetch saved board states for puzzle ids, in batches.

    Returns ``(states, player)``: the flattened list of per-puzzle state
    objects, plus the player block (lifetime stats, identical across batches).
    Each raw batch response is saved under data/ for re-parsing.

    Note: NYT only returns states for puzzles the user actually played, and
    only retains per-day boards for roughly the last ~10 months. Lifetime
    aggregate stats live in the player block regardless.
    """
    DATA_DIR.mkdir(exist_ok=True)
    states = []
    player = None
    for i in range(0, len(puzzle_ids), batch_size):
        batch = puzzle_ids[i : i + batch_size]
        ids = ",".join(str(pid) for pid in batch)
        data = get_json(STATE_URL.format(ids=ids), cookie=cookie)
        raw_path = DATA_DIR / f"states_{batch[0]}_{batch[-1]}.json"
        raw_path.write_text(json.dumps(data, indent=2))
        states.extend(data.get("states", []))
        if player is None and isinstance(data.get("player"), dict):
            player = data["player"]
        time.sleep(throttle)
    return states, player


def parse_states(states, index):
    """Flatten saved states into per-day rows joined with the solution.

    Each state has a ``game_data`` block (boardState, status, hardMode,
    currentRowIndex), a string ``puzzle_id``, and a ``print_date``. ``index``
    maps date -> {id, solution} (built from the public endpoint).
    """
    date_to_solution = {day: entry.get("solution") for day, entry in index.items()}
    rows = []
    for state in states:
        game = state.get("game_data", {})
        board = [row for row in game.get("boardState", []) if row]
        date = state.get("print_date")
        status = (game.get("status") or "").upper()
        rows.append(
            {
                "date": date,
                "puzzle_id": state.get("puzzle_id"),
                "solution": date_to_solution.get(date),
                "guesses": "|".join(board),
                "num_guesses": len(board),
                "won": status == "WIN",
                "hard_mode": bool(game.get("hardMode")),
                "status": status,
            }
        )
    rows.sort(key=lambda r: (r["date"] or ""))
    return rows


def write_csv(rows, path=OUTPUT_CSV):
    DATA_DIR.mkdir(exist_ok=True)
    fields = ["date", "puzzle_id", "solution", "guesses", "num_guesses", "won",
              "hard_mode", "status"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {len(rows)} rows to {path}")


def write_stats_summary(player, path=STATS_JSON):
    """Save the player's lifetime Wordle stats block (streaks, distribution)."""
    if not player:
        return
    wordle = player.get("stats", {}).get("wordle", {})
    path.write_text(json.dumps(wordle, indent=2))
    print(f"Wrote lifetime stats to {path}")


# --- CLI -------------------------------------------------------------------

def _parse_date(value):
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def download(start, end, batch_size):
    print(f"Building puzzle index {start} .. {end} ...")
    index = build_index(start, end)
    puzzle_ids = [entry["id"] for entry in index.values()]
    print(f"  {len(puzzle_ids)} puzzles in range.")
    cookie = load_cookie()
    print("Fetching saved game states ...")
    states, player = fetch_states(puzzle_ids, cookie, batch_size=batch_size)
    print(f"  {len(states)} states returned.")
    rows = parse_states(states, index)
    rows = [r for r in rows if r["puzzle_id"] is not None and r["num_guesses"] > 0]
    write_csv(rows)
    write_stats_summary(player)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("extract-cookie", help="Extract NYT-S from a saved webctl session")

    dl = sub.add_parser("download", help="Download personal Wordle history to CSV")
    dl.add_argument("--start", type=_parse_date, default=LAUNCH_DATE,
                    help="First date (YYYY-MM-DD), default Wordle launch")
    dl.add_argument("--end", type=_parse_date, default=dt.date.today(),
                    help="Last date (YYYY-MM-DD), default today")
    dl.add_argument("--batch-size", type=int, default=31,
                    help="puzzle_ids per state request")

    args = parser.parse_args()
    if args.command == "extract-cookie":
        extract_cookie()
    elif args.command == "download":
        download(args.start, args.end, args.batch_size)


if __name__ == "__main__":
    main()
