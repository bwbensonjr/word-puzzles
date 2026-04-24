import csv 
from collections import Counter
from io import TextIOWrapper
import urllib.request

HISTORY_URL = "https://stuckonwordle.s3.ap-southeast-2.amazonaws.com/wordle/history.csv"

def score_word(word, freqs):
    word_freqs = [freqs[i][letter] for i, letter in enumerate(word)]
    score = sum(word_freqs)/len(word)
    return score

def letter_freqs(words):
    num_words = len(words)
    freqs = []
    for i in range(5):
        counts = Counter([word[i] for word in words])
        freqs.append({letter: counts[letter]/num_words for letter in counts})
    return freqs

def get_wordal_history():
    words = [row["solution"] for row in read_url_csv(HISTORY_URL)]
    return words

def read_url_csv(url):
    with urllib.request.urlopen(url) as response:
        text_stream = TextIOWrapper(response, encoding="utf-8")
        reader = csv.DictReader(text_stream)
        rows = [row for row in reader]
    return rows

