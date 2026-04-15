import nltk

_analyzer = None


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        nltk.download("vader_lexicon", quiet=True)
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def analyze_sentiment(text: str) -> float:
    """Return VADER compound score in range -1.0 to 1.0."""
    scores = _get_analyzer().polarity_scores(text)
    return scores["compound"]
