import re
import nltk

_analyzer = None

# Negative context patterns that VADER misses.
# VADER scores individual words but misses phrases like "no sleep",
# "can't concentrate", "snapping at everyone" as negative.
_NEGATIVE_PATTERNS = [
    r"\bno sleep\b", r"\bcan'?t sleep\b", r"\bbarely slept?\b",
    r"\bcan'?t concentrate\b", r"\bcan'?t focus\b", r"\bcan'?t relax\b",
    r"\bsnapp(?:ing|ed)\b", r"\bskipp(?:ing|ed) meals?\b",
    r"\bskipp(?:ing|ed) (?:the )?gym\b",
    r"\bheart rac(?:es|ing)\b", r"\bmind (?:won'?t stop|racing)\b",
    r"\bpanic(?:king|ked)?\b", r"\bpanic attack\b",
    r"\bcried\b", r"\bcrying\b", r"\bbroke(?:n)? down\b",
    r"\bfeels? like too much\b", r"\beverything feels?\b.*\btoo much\b",
    r"\ball over again\b",  # "this feels like X all over again"
    r"\bcan'?t say no\b", r"\bcan'?t face\b",
    r"\bdrops?\b.*\bstomach\b", r"\bstomach drop\b",
]

_POSITIVE_PATTERNS = [
    r"\bfelt? (?:great|amazing|wonderful|incredible)\b",
    r"\bfeeling (?:better|hopeful|proud|grateful|strong)\b",
    r"\bslept? (?:well|good|\d+ hours)\b",
    r"\bpersonal record\b", r"\b(?:good|great|best) day\b",
]

_neg_compiled = [re.compile(p, re.IGNORECASE) for p in _NEGATIVE_PATTERNS]
_pos_compiled = [re.compile(p, re.IGNORECASE) for p in _POSITIVE_PATTERNS]


def _get_analyzer():
    global _analyzer
    if _analyzer is None:
        nltk.download("vader_lexicon", quiet=True)
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def analyze_sentiment(text: str) -> float:
    """Return adjusted VADER compound score in range -1.0 to 1.0.

    Uses VADER as the base, then applies context-aware corrections
    for patterns VADER systematically misses (negation + mental health language).
    """
    base_score = _get_analyzer().polarity_scores(text)["compound"]

    # Count contextual pattern matches
    neg_hits = sum(1 for p in _neg_compiled if p.search(text))
    pos_hits = sum(1 for p in _pos_compiled if p.search(text))

    # Apply corrections
    adjustment = (pos_hits * 0.15) - (neg_hits * 0.25)
    corrected = base_score + adjustment

    # Clamp to [-1.0, 1.0]
    return max(-1.0, min(1.0, corrected))
