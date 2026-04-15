from collections import Counter

import nltk

_stop_words = None


def _get_stop_words():
    global _stop_words
    if _stop_words is None:
        nltk.download("punkt_tab", quiet=True)
        nltk.download("stopwords", quiet=True)
        from nltk.corpus import stopwords
        _stop_words = set(stopwords.words("english"))
    return _stop_words


def extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Extract top keywords from text using tokenization + stop word removal."""
    from nltk.tokenize import word_tokenize
    stop_words = _get_stop_words()
    tokens = word_tokenize(text.lower())
    filtered = [
        t for t in tokens
        if t.isalpha() and t not in stop_words and len(t) > 2
    ]
    freq = Counter(filtered)
    return [word for word, _ in freq.most_common(max_keywords)]
