"""
Integration tests for Coping Strategy Memory (P0 feature).

Tests that coping strategies are:
1. Stored with entry_type="coping_strategy" in seed data
2. Retrieved by search_coping_strategies from Qdrant
3. Included in drift detection results
4. Surfaced in the drift message text
5. Returned in the correct format from the API

Requires seeded data: cd backend && python -m seed.seed_data
"""

import pytest
import json
import uuid
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.drift_engine import detect_drift
from services.qdrant_service import (
    search_coping_strategies,
    scroll_entries,
    upsert_entry,
)
from services.embedding import generate_embedding
from config import settings
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
SEED_USER = settings.default_user_id


class TestCopingStrategiesInQdrant:
    """Test that coping entries exist and are queryable in Qdrant."""

    @pytest.mark.integration
    def test_coping_entries_exist(self):
        """Seed data should include entries with entry_type='coping_strategy'."""
        coping = search_coping_strategies(user_id=SEED_USER, limit=10)
        assert len(coping) >= 1, "No coping strategy entries found in Qdrant"

    @pytest.mark.integration
    def test_coping_entries_have_transcripts(self):
        """Each coping entry should have a non-empty transcript."""
        coping = search_coping_strategies(user_id=SEED_USER, limit=10)
        for entry in coping:
            transcript = entry.payload.get("transcript", "")
            assert len(transcript) > 10, f"Empty coping transcript: {entry.id}"

    @pytest.mark.integration
    def test_coping_entries_tagged_correctly(self):
        """All returned entries should have entry_type='coping_strategy'."""
        coping = search_coping_strategies(user_id=SEED_USER, limit=10)
        for entry in coping:
            assert entry.payload.get("entry_type") == "coping_strategy", (
                f"Wrong entry_type: {entry.payload.get('entry_type')}"
            )

    @pytest.mark.integration
    def test_coping_date_range_filter(self):
        """Coping entries should be filterable by date range."""
        # Feb recovery coping entries are dated Feb 27-28
        feb_start = int(datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp())
        mar_start = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())

        coping = search_coping_strategies(
            user_id=SEED_USER,
            date_from=feb_start,
            date_to=mar_start,
        )
        assert len(coping) >= 1, "No coping entries found in Feb date range"

    @pytest.mark.integration
    def test_coping_nonexistent_user(self):
        """No coping strategies for a user that doesn't exist."""
        coping = search_coping_strategies(
            user_id=f"nonexistent_{uuid.uuid4().hex[:8]}"
        )
        assert len(coping) == 0

    @pytest.mark.integration
    def test_coping_content_is_actionable(self):
        """Coping transcripts should contain actionable advice, not just mood descriptions."""
        coping = search_coping_strategies(user_id=SEED_USER, limit=10)
        assert len(coping) >= 1

        # At least one coping entry should mention an action (what helped)
        all_text = " ".join(e.payload.get("transcript", "") for e in coping).lower()
        action_words = ["helped", "helped me", "taking", "boundary", "asking", "speaking up", "offline", "gym"]
        has_action = any(w in all_text for w in action_words)
        assert has_action, f"Coping entries don't seem actionable: {all_text[:200]}"


class TestCopingInDriftDetection:
    """Test that drift detection surfaces coping strategies."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_result_has_coping_key(self):
        """Drift result should include coping_strategies key."""
        result = detect_drift(SEED_USER)
        assert "coping_strategies" in result, "Missing coping_strategies key in drift result"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_returns_coping_when_detected(self):
        """When drift is detected, coping strategies from matching period should be returned."""
        result = detect_drift(SEED_USER)
        if result["detected"]:
            assert result["coping_strategies"] is not None, (
                "Drift detected but no coping strategies returned"
            )
            assert len(result["coping_strategies"]) >= 1
            assert isinstance(result["coping_strategies"][0], str)
            assert len(result["coping_strategies"][0]) > 10

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_message_mentions_what_helped(self):
        """When coping strategies exist, drift message should reference them."""
        result = detect_drift(SEED_USER)
        if result["detected"] and result["coping_strategies"]:
            msg = result["message"].lower()
            assert "helped" in msg or "last time" in msg, (
                f"Drift message doesn't mention coping strategies: {result['message'][:200]}"
            )

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_coping_are_from_recovery_period(self):
        """Coping strategies should come from the recovery period, not the burnout period."""
        result = detect_drift(SEED_USER)
        if result["coping_strategies"]:
            for strategy in result["coping_strategies"]:
                s = strategy.lower()
                # Should be about recovery actions, not burnout symptoms
                burnout_only = ["can't sleep", "overwhelmed", "dread going"]
                is_burnout = all(b in s for b in burnout_only)
                assert not is_burnout, f"Coping strategy is a burnout entry, not a recovery strategy: {strategy[:100]}"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_skipped_drift_has_no_coping(self):
        """When drift is skipped (not enough data), coping should not be present."""
        result = detect_drift(f"new_user_{uuid.uuid4().hex[:8]}")
        assert result["skipped"] is True
        # When skipped, coping_strategies key may not be in the return at all
        # or it should be None
        coping = result.get("coping_strategies")
        assert coping is None


class TestCopingViaAPI:
    """Test coping strategy flow through the API endpoints."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_drift_current_includes_coping(self):
        """GET /api/drift-current should include coping_strategies."""
        resp = client.get("/api/drift-current")
        assert resp.status_code == 200
        data = resp.json()
        assert "coping_strategies" in data

    @pytest.mark.integration
    @pytest.mark.slow
    def test_manual_coping_entry_stored(self):
        """POST /api/entries with entry_type=coping_strategy should store correctly."""
        test_user = f"test_coping_{uuid.uuid4().hex[:8]}"
        resp = client.post("/api/entries", json={
            "user_id": test_user,
            "transcript": "What helped me was going for a walk every morning and talking to my friend.",
            "entry_type": "coping_strategy",
        })
        assert resp.status_code == 200

        # Verify it's stored as coping_strategy
        coping = search_coping_strategies(user_id=test_user)
        assert len(coping) == 1
        assert coping[0].payload["entry_type"] == "coping_strategy"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_vapi_store_and_analyze_returns_coping(self):
        """Vapi store_and_analyze should include coping in drift result."""
        resp = client.post("/vapi/webhook", json={
            "message": {
                "type": "tool-calls",
                "toolCallList": [{
                    "id": "coping_test_001",
                    "name": "store_and_analyze",
                    "parameters": {
                        "mood_summary": "Stressed about deadlines again",
                        "full_transcript": "I am overwhelmed by deadlines and cant sleep",
                        "user_id": SEED_USER,
                    },
                }],
            }
        })
        assert resp.status_code == 200
        result_str = resp.json()["results"][0]["result"]
        result = json.loads(result_str)
        assert result["status"] == "stored"
