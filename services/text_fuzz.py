"""Typo tolerance for customer text: "puna", "vishwajit emipre", "swiming pool", "tommorow".

Each matcher corrects words against its own vocabulary (place names, project words, amenity words,
dates), so a correction can only ever produce a word that matcher already understands.
"""
import re
from difflib import get_close_matches

# Common words that sit within typo distance of a real name and must never be "corrected":
# "than" -> "thane", "pure" -> "pune", "price" -> "prime", "town" stays a word, etc.
STOPWORDS = frozenset("""
    than then there their these those where were here near need what when which with will want wants
    pure price prices prize prime time home homes some same more most also only into from your about
    have give take make show tell help like book look good best rate rates date open plan plans
    flat flats unit units size sizes area areas room rooms floor floors wing wings park part
""".split())


def correct_words(text, vocabulary, cutoff=0.8, min_len=4):
    """`text` with each unknown word of `min_len`+ letters replaced by its closest vocabulary word, if one
    is within `cutoff` similarity. Known words, stopwords and short words are left alone."""
    vocabulary = {w.lower() for w in vocabulary if w}
    candidates = sorted(vocabulary)

    def fix(match):
        word = match.group(0)
        lowered = word.lower()
        if len(lowered) < min_len or lowered in vocabulary or lowered in STOPWORDS:
            return word
        close = get_close_matches(lowered, candidates, n=1, cutoff=cutoff)
        return close[0] if close else word

    return re.sub(r"[A-Za-z]+", fix, str(text or ""))
