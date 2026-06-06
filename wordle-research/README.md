# Research on Wordle words

## Global solution history

History URL - https://stuckonwordle.s3.ap-southeast-2.amazonaws.com/wordle/history.csv

`wordle_history.py` fetches the public list of past Wordle solutions and
computes per-position letter frequencies.

## Personal play history

`nyt_history.py` downloads *your own* saved Wordle games from the NYT (your
guesses, win/loss, per-day) into `data/wordle_personal_history.csv`.

It uses two sources:

- The public per-date endpoint `https://www.nytimes.com/svc/wordle/v2/YYYY-MM-DD.json`
  for the puzzle `id` and the day's `solution`. NYT assigns puzzle ids from a
  non-chronological pool, so they're looked up and cached in
  `data/puzzle_index.json`.
- The authenticated endpoint `.../svc/games/state/wordleV2/latests?puzzle_ids=...`
  for your saved board and stats. This needs the `NYT-S` session cookie.

### One-time: get the NYT-S cookie via webctl

```bash
webctl navigate "https://www.nytimes.com/account/login"
webctl prompt-secret          # type your NYT email/password, then submit
webctl wait network-idle
webctl save "nyt"             # persists cookies to a session profile

uv run python nyt_history.py extract-cookie   # pulls NYT-S into .nyt_cookie
```

Alternatively, set the cookie directly: `export NYT_S=<value>`.
The cookie is a secret — `.nyt_cookie` and `data/` are gitignored. The
`NYT-S` cookie expires after several months; re-run the login if you get a
`403`.

### Download

```bash
uv run python nyt_history.py download                          # full history
uv run python nyt_history.py download --start 2025-08-01 --end 2026-06-06
```

Output:
- `data/wordle_personal_history.csv` — one row per played day: `date`,
  `puzzle_id`, `solution`, `guesses` (pipe-joined), `num_guesses`, `won`,
  `hard_mode`, `status`.
- `data/wordle_stats.json` — your lifetime Wordle stats (streaks, total games,
  guess distribution).
- Raw JSON batches under `data/` for re-parsing.

**Retention:** NYT only returns per-day boards for roughly the last ~10
months (and only for days you actually played). Lifetime *aggregate* stats in
`wordle_stats.json` go back further than the per-day boards. Requesting a
wider range is harmless — unavailable days are simply absent.
