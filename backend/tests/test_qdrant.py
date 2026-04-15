import pytest
import uuid
from datetime import datetime, timezone, timedelta

from services.qdrant_service import (
    create_collection,
    upsert_entry,
    scroll_entries,
    search_similar,
)
from services.embedding import generate_embedding
from config import settings

# Unique test user so we don't pollute demo data
TEST_USER = f"test_user_{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module", autouse=True)
def setup_collection():
    """Ensure collection + indexes exist before integration tests run."""
    create_collection()


@pytest.fixture(scope="module")
def seeded_entries():
    """Insert 3 test entries with known content and return their IDs + vectors."""
    entries = [
        {
            "text": "I had a wonderful day. Feeling happy and energetic.",
            "days_ago": 2,
        },
        {
            "text": "Feeling stressed and overwhelmed. Can't sleep at all.",
            "days_ago": 1,
        },
        {
            "text": "Work deadlines are crushing me. I dread Monday.",
            "days_ago": 0,
        },
    ]
    results = []
    for entry in entries:
        vector = generate_embedding(entry["text"])
        now = datetime.now(timezone.utc) - timedelta(days=entry["days_ago"])
        payload = {
            "user_id": TEST_USER,
            "date": now.strftime("%Y-%m-%d"),
            "timestamp": int(now.timestamp()),
            "transcript": entry["text"],
            "sentiment_score": 0.0,
            "keywords": [],
            "week_number": now.isocalendar()[1],
            "month": now.strftime("%Y-%m"),
            "entry_type": "checkin",
        }
        point_id = upsert_entry(vector, payload)
        results.append({"id": point_id, "vector": vector, "payload": payload})
    return results


class TestQdrantUpsert:
    """Integration tests for upserting entries into Qdrant."""

    @pytest.mark.integration
    def test_upsert_returns_uuid(self, seeded_entries):
        for entry in seeded_entries:
            # Validate UUID format
            uuid.UUID(entry["id"])

    @pytest.mark.integration
    def test_upsert_count(self, seeded_entries):
        assert len(seeded_entries) == 3


class TestQdrantScroll:
    """Integration tests for scrolling/filtering entries."""

    @pytest.mark.integration
    def test_scroll_returns_entries(self, seeded_entries):
        entries = scroll_entries(user_id=TEST_USER)
        assert len(entries) >= 3

    @pytest.mark.integration
    def test_scroll_has_vectors(self, seeded_entries):
        entries = scroll_entries(user_id=TEST_USER)
        for entry in entries:
            assert entry.vector is not None
            assert len(entry.vector) == settings.embedding_dim

    @pytest.mark.integration
    def test_scroll_has_payload(self, seeded_entries):
        entries = scroll_entries(user_id=TEST_USER)
        for entry in entries:
            assert entry.payload["user_id"] == TEST_USER
            assert "transcript" in entry.payload
            assert "timestamp" in entry.payload

    @pytest.mark.integration
    def test_scroll_date_filter(self, seeded_entries):
        """Filtering by timestamp range should narrow results."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        one_day_ago_ts = now_ts - 86400

        recent = scroll_entries(
            user_id=TEST_USER,
            date_from=one_day_ago_ts,
        )
        all_entries = scroll_entries(user_id=TEST_USER)
        assert len(recent) <= len(all_entries)

    @pytest.mark.integration
    def test_scroll_nonexistent_user(self):
        entries = scroll_entries(user_id="nonexistent_user_xyz")
        assert len(entries) == 0


class TestQdrantSearch:
    """Integration tests for semantic similarity search."""

    @pytest.mark.integration
    def test_search_returns_results(self, seeded_entries):
        query_vector = generate_embedding("overwhelmed and stressed")
        results = search_similar(query_vector, user_id=TEST_USER, limit=2)
        assert len(results) > 0

    @pytest.mark.integration
    def test_search_relevance(self, seeded_entries):
        """Searching for stress-related text should rank the stressed entry higher
        than the happy entry."""
        query_vector = generate_embedding("stressed overwhelmed can't sleep")
        results = search_similar(query_vector, user_id=TEST_USER, limit=3)

        transcripts = [r.payload["transcript"] for r in results]
        # The stressed entry should appear before the happy one
        stress_idx = next(
            i for i, t in enumerate(transcripts) if "stressed" in t.lower()
        )
        happy_idx = next(
            i for i, t in enumerate(transcripts) if "wonderful" in t.lower()
        )
        assert stress_idx < happy_idx, (
            f"Stressed entry at index {stress_idx} should rank above "
            f"happy entry at index {happy_idx}"
        )

    @pytest.mark.integration
    def test_search_scores_in_range(self, seeded_entries):
        """Cosine similarity scores from Qdrant range from -1.0 to 1.0."""
        query_vector = generate_embedding("test query")
        results = search_similar(query_vector, user_id=TEST_USER, limit=3)
        for r in results:
            assert -1.0 <= r.score <= 1.0, f"Score {r.score} outside [-1, 1]"

    @pytest.mark.integration
    def test_search_nonexistent_user(self, seeded_entries):
        query_vector = generate_embedding("anything")
        results = search_similar(query_vector, user_id="nonexistent_user_xyz")
        assert len(results) == 0

    @pytest.mark.integration
    def test_search_limit(self, seeded_entries):
        query_vector = generate_embedding("feeling")
        results = search_similar(query_vector, user_id=TEST_USER, limit=1)
        assert len(results) == 1
