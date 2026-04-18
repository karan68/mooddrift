import pytest

from models.schemas import MoodEntryPayload, MoodEntryCreate, MoodEntryResponse


class TestMoodEntryPayload:
    """Unit tests for the MoodEntryPayload Pydantic model."""

    @pytest.mark.unit
    def test_valid_payload(self):
        payload = MoodEntryPayload(
            user_id="user_123",
            date="2026-04-14",
            timestamp=1744656000,
            transcript="I'm feeling great today.",
            sentiment_score=0.8,
            keywords=["great", "feeling"],
            week_number=16,
            month="2026-04",
            entry_type="checkin",
        )
        assert payload.user_id == "user_123"
        assert payload.sentiment_score == 0.8
        assert payload.keywords == ["great", "feeling"]

    @pytest.mark.unit
    def test_default_entry_type(self):
        payload = MoodEntryPayload(
            user_id="u1",
            date="2026-01-01",
            timestamp=1,
            transcript="test",
            sentiment_score=0.0,
            keywords=[],
            week_number=1,
            month="2026-01",
        )
        assert payload.entry_type == "checkin"

    @pytest.mark.unit
    def test_missing_required_field(self):
        with pytest.raises(Exception):
            MoodEntryPayload(
                user_id="u1",
                # date missing
                timestamp=1,
                transcript="test",
                sentiment_score=0.0,
                keywords=[],
                week_number=1,
                month="2026-01",
            )

    @pytest.mark.unit
    def test_serialization_roundtrip(self):
        data = {
            "user_id": "user_123",
            "date": "2026-04-14",
            "timestamp": 1744656000,
            "transcript": "test entry",
            "sentiment_score": -0.5,
            "keywords": ["stress", "work"],
            "week_number": 16,
            "month": "2026-04",
            "entry_type": "reflection",
        }
        payload = MoodEntryPayload(**data)
        dumped = payload.model_dump()
        # Compare only the keys we provided; optional biomarker fields default to None
        for key, value in data.items():
            assert dumped[key] == value


class TestMoodEntryCreate:
    """Unit tests for MoodEntryCreate."""

    @pytest.mark.unit
    def test_valid_create(self):
        entry = MoodEntryCreate(
            user_id="user_123",
            transcript="Today was tough.",
        )
        assert entry.entry_type == "checkin"

    @pytest.mark.unit
    def test_custom_entry_type(self):
        entry = MoodEntryCreate(
            user_id="u1",
            transcript="reflection",
            entry_type="reflection",
        )
        assert entry.entry_type == "reflection"


class TestMoodEntryResponse:
    """Unit tests for MoodEntryResponse."""

    @pytest.mark.unit
    def test_optional_score(self):
        resp = MoodEntryResponse(
            id="abc-123",
            payload=MoodEntryPayload(
                user_id="u1",
                date="2026-01-01",
                timestamp=1,
                transcript="test",
                sentiment_score=0.0,
                keywords=[],
                week_number=1,
                month="2026-01",
            ),
        )
        assert resp.score is None

    @pytest.mark.unit
    def test_with_score(self):
        resp = MoodEntryResponse(
            id="abc-123",
            payload=MoodEntryPayload(
                user_id="u1",
                date="2026-01-01",
                timestamp=1,
                transcript="test",
                sentiment_score=0.0,
                keywords=[],
                week_number=1,
                month="2026-01",
            ),
            score=0.95,
        )
        assert resp.score == 0.95
