from collections import Counter

import nltk

nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

_stop_words = set(stopwords.words("english"))


def extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Extract top keywords from text using tokenization + stop word removal."""
    tokens = word_tokenize(text.lower())
    filtered = [
        t for t in tokens
        if t.isalpha() and t not in _stop_words and len(t) > 2
    ]
    freq = Counter(filtered)
    return [word for word, _ in freq.most_common(max_keywords)]
