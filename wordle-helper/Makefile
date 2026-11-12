DICT = /usr/share/dict/words
# Past Wordle answers, cached by wordle-research/nyt_history.py (gitignored).
INDEX = ../wordle-research/data/puzzle_index.json

all: word-list-5.txt

# Hand-added words missing from the dictionary (originally commit 5ee96f4).
EXTRA = extra-words.txt

# Lowercase-only dictionary entries (drops proper nouns), the hand-added
# extras, and every past Wordle answer, since the dictionary lacks newer
# words like "emoji".
word-list-5.txt: $(DICT) $(EXTRA) $(wildcard $(INDEX))
	{ LC_ALL=C grep -x '[a-z]\{5\}' $(DICT); \
	  cat $(EXTRA); \
	  if [ -f $(INDEX) ]; then \
	    python3 -c 'import json, sys; print("\n".join(v["solution"] for v in json.load(open(sys.argv[1])).values()))' $(INDEX); \
	  else \
	    echo "warning: $(INDEX) not found; past answers not added" >&2; \
	  fi; } | LC_ALL=C sort -u > $@
