import pytest
from datetime import datetime, timezone

from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.embedding import generate_embedding


class TestFullPipeline:
    """End-to-end unit tests: transcript → sentiment + keywords + embedding."""

    @pytest.mark.slow
    @pytest.mark.unit
    def test_pipeline_positive_entry(self):
        text = "I had an amazing day! Gym felt great, had coffee with a friend."
        score = analyze_sentiment(text)
        keywords = extract_keywords(text)
        vector = generate_embedding(text)

        assert score > 0
        assert len(keywords) > 0
        assert len(vector) == 384

    @pytest.mark.slow
    @pytest.mark.unit
    def test_pipeline_negative_entry(self):
        text = (
            "I'm overwhelmed. My manager keeps piling on work. "
            "I barely slept. I dread going in tomorrow."
        )
        score = analyze_sentiment(text)
        keywords = extract_keywords(text)
        vector = generate_embedding(text)

        assert score < 0
        assert len(keywords) > 0
        assert len(vector) == 384

    @pytest.mark.slow
    @pytest.mark.unit
    def test_pipeline_builds_valid_payload(self):
        """Simulate what the real entry handler will do."""
        text = "Feeling okay today. Nothing exciting, just normal."
        now = datetime.now(timezone.utc)

        score = analyze_sentiment(text)
        keywords = extract_keywords(text)
        vector = generate_embedding(text)

        payload = {
            "user_id": "test_user",
            "date": now.strftime("%Y-%m-%d"),
            "timestamp": int(now.timestamp()),
            "transcript": text,
            "sentiment_score": score,
            "keywords": keywords,
            "week_number": now.isocalendar()[1],
            "month": now.strftime("%Y-%m"),
            "entry_type": "checkin",
        }

        # Validate payload shape
        assert isinstance(payload["timestamp"], int)
        assert isinstance(payload["sentiment_score"], float)
        assert isinstance(payload["keywords"], list)
        assert len(vector) == 384
