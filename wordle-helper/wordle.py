import re
import sys
from collections import Counter

WORD_FILE = "word-list-5.txt"

def main():
    pattern = sys.argv[1]
    print(pattern)
    if len(sys.argv) > 2:
        out_letters = sys.argv[2]
    else:
        out_letters = None
    if len(sys.argv) == 4:
        in_letters = sys.argv[3]
    else:
        in_letters = None
    sorted_scored = matching_word_list(pattern, out_letters=out_letters, in_letters=in_letters)
    for word in sorted_scored:
        print(word)

def matching_word_list(pattern, out_letters, in_letters):
    matching_words = matching(pattern, out_letters=out_letters, in_letters=in_letters)
    counters = calculate_weights(matching_words)
    scores = [score_word(word, counters) for word in matching_words]
    sorted_scored = []
    for score, word in sorted(zip(scores, matching_words)):
        num_reps = num_repeats(word)
        if num_reps > 0:
            repeat_info = f"{num_reps}"
        else:
            repeat_info = ""
        sorted_scored.append(f"{score}: {word} {repeat_info}")
    return sorted_scored
    
        
def matching(expr_string, out_letters=None, in_letters=None):
    expr = re.compile("^" + expr_string + "$")
    with open(WORD_FILE) as wf:
        words = sorted(wf.read().split())
    matching_words = []
    for word in words:
        m = expr.match(word)
        if m:
            if out_letters:
                if any(letter in word for letter in out_letters):
                    continue
            if in_letters:
                if any(letter not in word for letter in in_letters):
                    continue
            matching_words.append(word)
    return matching_words

def calculate_weights(words):
    counters = []
    for i in range(0, 5):
        counter = Counter([w[i] for w in words])
        counters.append(counter)
    return counters

def score_word(word, counters):
    score = sum([counters[i][word[i]] for i in range(0, 5)])
    return score

def num_repeats(word):
    c = Counter(word)
    num_reps = sum((v - 1) for v in c.values() if v > 1)
    return num_reps

def has_repeats(word):
    c = Counter(word)
    for ch in c:
        if c[ch] > 1:
            return True
    return False

if __name__ == "__main__":
    main()
