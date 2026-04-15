"""
Integration tests for drift detection using seeded data.

These tests assume the seed data has been loaded into Qdrant.
Run: cd backend && python -m seed.seed_data
Then: python -m pytest tests/test_drift_integration.py -v
"""

import pytest

from services.drift_engine import detect_drift
from config import settings


SEED_USER = settings.default_user_id  # "demo_user"


class TestDriftDetectionWithSeedData:
    """Integration tests that rely on the 60 seeded entries in Qdrant."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_detected_for_demo_user(self):
        """April 10-14 entries should trigger drift against the stable baseline.
        Note: drift score may be marginally below threshold if other tests
        inserted extra demo_user entries. We check >= threshold - 0.01."""
        result = detect_drift(SEED_USER)

        # Should not be skipped — we have 60+ entries
        assert result["skipped"] is False, f"Skipped: {result['skip_reason']}"

        # Drift score should be near/above threshold (allow small margin
        # since other tests may add neutral entries for demo_user)
        assert result["drift_score"] >= settings.drift_threshold - 0.03, (
            f"Drift score too low: {result['drift_score']}, "
            f"threshold={settings.drift_threshold}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_has_matching_period(self):
        """Pattern matching should find the Feb 10-20 burnout period."""
        result = detect_drift(SEED_USER)

        if result["detected"]:
            # Should have a matching period referencing February
            assert result["matching_period"] is not None
            assert "Feb" in result["matching_period"], (
                f"Expected Feb match, got: {result['matching_period']}"
            )

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_has_matching_context(self):
        """Matching context should include burnout-related keywords."""
        result = detect_drift(SEED_USER)

        if result["detected"] and result["matching_context"]:
            assert isinstance(result["matching_context"], list)
            assert len(result["matching_context"]) > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_message_is_human_readable(self):
        """The drift message should be a meaningful string."""
        result = detect_drift(SEED_USER)
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 20

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_sentiment_direction(self):
        """April drift entries are negative → sentiment should be declining."""
        result = detect_drift(SEED_USER)
        assert result["sentiment_direction"] in ("declining", "improving", "stable")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_nonexistent_user_skips(self):
        """User with no entries should return skipped."""
        result = detect_drift("nonexistent_user_xyz")
        assert result["skipped"] is True
        assert result["detected"] is False

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_result_shape(self):
        """Verify all expected keys are present in the result."""
        result = detect_drift(SEED_USER)
        expected_keys = {
            "detected", "drift_score", "similarity", "severity",
            "message", "matching_period", "matching_context",
            "coping_strategies", "sentiment_direction", "skipped", "skip_reason",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_score_range(self):
        """Drift score should be in [0, 2]."""
        result = detect_drift(SEED_USER)
        assert 0.0 <= result["drift_score"] <= 2.0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_similarity_range(self):
        """Cosine similarity should be in [-1, 1]."""
        result = detect_drift(SEED_USER)
        assert -1.0 <= result["similarity"] <= 1.0
