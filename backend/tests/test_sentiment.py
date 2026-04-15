import pytest

from services.sentiment import analyze_sentiment


class TestSentiment:
    """Unit tests for VADER sentiment analysis."""

    @pytest.mark.unit
    def test_negative_text(self):
        score = analyze_sentiment(
            "I'm feeling terrible. Everything is going wrong."
        )
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0
        assert score < 0, f"Expected negative score, got {score}"

    @pytest.mark.unit
    def test_positive_text(self):
        score = analyze_sentiment(
            "I'm feeling amazing! Had a wonderful day at work."
        )
        assert isinstance(score, float)
        assert score > 0, f"Expected positive score, got {score}"

    @pytest.mark.unit
    def test_neutral_text(self):
        score = analyze_sentiment("I went to the store today.")
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0

    @pytest.mark.unit
    def test_score_range(self):
        """VADER compound always in [-1.0, 1.0]."""
        texts = [
            "WORST DAY EVER!!! I HATE EVERYTHING!",
            "Best day of my life, absolutely incredible!",
            "",
            "okay",
        ]
        for text in texts:
            score = analyze_sentiment(text)
            assert -1.0 <= score <= 1.0, f"Out of range for: {text!r}"

    @pytest.mark.unit
    def test_empty_string(self):
        score = analyze_sentiment("")
        assert score == 0.0

    @pytest.mark.unit
    def test_burnout_language(self):
        """Text matching the seed data burnout arc should score negative."""
        score = analyze_sentiment(
            "I'm overwhelmed. Can't sleep, maybe 4 hours a night. "
            "I dread going to work."
        )
        assert score < 0
