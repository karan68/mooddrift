import nltk

nltk.download("vader_lexicon", quiet=True)

from nltk.sentiment.vader import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()


def analyze_sentiment(text: str) -> float:
    """Return VADER compound score in range -1.0 to 1.0."""
    scores = _analyzer.polarity_scores(text)
    return scores["compound"]
