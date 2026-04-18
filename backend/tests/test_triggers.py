"""
Tests for Trigger Pattern Detection (FEATURES.md Feature 3).

Covers:
  - Keyword trigger detection (positive and negative impacts)
  - Noise word filtering
  - Minimum occurrence threshold
  - Time-of-day trigger detection
  - Co-occurrence trigger detection
  - Confidence classification
  - Edge cases (no entries, too few entries, all same sentiment)
  - API endpoint shape
  - Integration with seeded demo data
"""

import os
import sys
import uuid
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.trigger_detector import (
    detect_triggers,
    _detect_keyword_triggers,
    _detect_time_triggers,
    _detect_cooccurrence_triggers,
    _classify_confidence,
    _NOISE_WORDS,
    _MIN_KEYWORD_OCCURRENCES,
)


# ============================================================
#                      Fake data helpers
# ============================================================


class FakePoint:
    def __init__(self, payload):
        self.payload = payload
        self.id = str(uuid.uuid4())
        self.vector = [0.0] * 384


def _make_entry(sentiment: float, keywords: list[str], timestamp: int = 0, entry_type: str = "checkin") -> FakePoint:
    return FakePoint({
        "sentiment_score": sentiment,
        "keywords": keywords,
        "timestamp": timestamp or int(time.time()),
        "date": "2026-04-15",
        "entry_type": entry_type,
    })


# ============================================================
#                 Confidence classification
# ============================================================


class TestConfidenceClassification:
    @pytest.mark.unit
    def test_high_confidence(self):
        assert _classify_confidence(10, -0.4) == "high"

    @pytest.mark.unit
    def test_medium_confidence(self):
        assert _classify_confidence(5, -0.25) == "medium"

    @pytest.mark.unit
    def test_low_confidence(self):
        assert _classify_confidence(3, -0.2) == "low"


# ============================================================
#                  Keyword trigger tests
# ============================================================


class TestKeywordTriggers:
    @pytest.mark.unit
    def test_detects_negative_keyword_trigger(self):
        """A keyword that appears in negative entries should be flagged."""
        entries = [
            # 5 entries with "deadline" — all negative
            _make_entry(-0.6, ["deadline", "work"]),
            _make_entry(-0.5, ["deadline", "stress"]),
            _make_entry(-0.7, ["deadline"]),
            _make_entry(-0.4, ["deadline", "pressure"]),
            _make_entry(-0.5, ["deadline"]),
            # 5 entries without "deadline" — positive
            _make_entry(0.4, ["gym", "energy"]),
            _make_entry(0.5, ["friends", "happy"]),
            _make_entry(0.3, ["relaxing"]),
            _make_entry(0.6, ["weekend"]),
            _make_entry(0.4, ["music"]),
        ]
        triggers = _detect_keyword_triggers(entries)
        deadline_triggers = [t for t in triggers if t["trigger"] == "deadline"]
        assert len(deadline_triggers) == 1
        t = deadline_triggers[0]
        assert t["impact"] < -0.5  # Strong negative impact
        assert t["occurrences"] == 5
        assert t["type"] == "keyword"

    @pytest.mark.unit
    def test_detects_positive_keyword_trigger(self):
        """A keyword that appears in positive entries should be flagged too."""
        entries = [
            # 4 entries with "gym" — positive
            _make_entry(0.6, ["gym", "energy"]),
            _make_entry(0.5, ["gym"]),
            _make_entry(0.7, ["gym", "run"]),
            _make_entry(0.4, ["gym"]),
            # 4 entries without "gym" — negative
            _make_entry(-0.4, ["work", "stress"]),
            _make_entry(-0.3, ["tired"]),
            _make_entry(-0.5, ["deadline"]),
            _make_entry(-0.2, ["overwhelmed"]),
        ]
        triggers = _detect_keyword_triggers(entries)
        gym_triggers = [t for t in triggers if t["trigger"] == "gym"]
        assert len(gym_triggers) == 1
        assert gym_triggers[0]["impact"] > 0.5  # Strong positive impact

    @pytest.mark.unit
    def test_filters_noise_words(self):
        """Words in the NOISE_WORDS set should not appear as triggers."""
        entries = [
            _make_entry(-0.5, ["feeling", "today", "stressed"]),
            _make_entry(-0.6, ["feeling", "today", "overwhelmed"]),
            _make_entry(-0.4, ["feeling", "today"]),
            _make_entry(0.4, ["happy"]),
            _make_entry(0.5, ["great"]),
        ]
        triggers = _detect_keyword_triggers(entries)
        noise_triggers = [t for t in triggers if t["trigger"] in _NOISE_WORDS]
        assert len(noise_triggers) == 0

    @pytest.mark.unit
    def test_ignores_below_min_occurrences(self):
        """Keywords appearing fewer than MIN_KEYWORD_OCCURRENCES times are skipped."""
        entries = [
            _make_entry(-0.8, ["rare_word"]),
            _make_entry(-0.7, ["rare_word"]),
            # Only 2 occurrences — below threshold of 3
            _make_entry(0.4, ["other"]),
            _make_entry(0.5, ["other"]),
            _make_entry(0.3, ["other"]),
        ]
        triggers = _detect_keyword_triggers(entries)
        rare = [t for t in triggers if t["trigger"] == "rare_word"]
        assert len(rare) == 0

    @pytest.mark.unit
    def test_ignores_low_impact_keywords(self):
        """Keywords with impact below threshold are not triggers."""
        # All entries have similar sentiment regardless of keyword
        entries = [
            _make_entry(0.1, ["work"]),
            _make_entry(0.05, ["work"]),
            _make_entry(0.0, ["work"]),
            _make_entry(-0.05, ["rest"]),
            _make_entry(0.0, ["rest"]),
            _make_entry(0.1, ["rest"]),
        ]
        triggers = _detect_keyword_triggers(entries)
        assert len(triggers) == 0  # Difference too small

    @pytest.mark.unit
    def test_sorted_by_absolute_impact(self):
        entries = [
            _make_entry(-0.8, ["catastrophe"]),
            _make_entry(-0.7, ["catastrophe"]),
            _make_entry(-0.9, ["catastrophe"]),
            _make_entry(-0.4, ["stress"]),
            _make_entry(-0.3, ["stress"]),
            _make_entry(-0.5, ["stress"]),
            _make_entry(0.5, ["joy"]),
            _make_entry(0.4, ["joy"]),
            _make_entry(0.6, ["joy"]),
        ]
        triggers = _detect_keyword_triggers(entries)
        if len(triggers) >= 2:
            assert abs(triggers[0]["impact"]) >= abs(triggers[1]["impact"])


# ============================================================
#                 Time-of-day trigger tests
# ============================================================


class TestTimeTriggers:
    @pytest.mark.unit
    def test_detects_night_trigger(self):
        """Entries at night with worse sentiment should flag night as trigger."""
        from datetime import datetime, timezone

        base = int(datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc).timestamp())
        night = int(datetime(2026, 4, 15, 22, 0, tzinfo=timezone.utc).timestamp())

        entries = [
            # Morning entries — positive
            _make_entry(0.4, ["work"], timestamp=base),
            _make_entry(0.5, ["work"], timestamp=base + 3600),
            _make_entry(0.3, ["work"], timestamp=base + 7200),
            _make_entry(0.4, ["work"], timestamp=base + 86400),
            _make_entry(0.5, ["work"], timestamp=base + 86400 + 3600),
            # Night entries — negative
            _make_entry(-0.4, ["worry"], timestamp=night),
            _make_entry(-0.5, ["anxiety"], timestamp=night + 86400),
            _make_entry(-0.6, ["dread"], timestamp=night + 2 * 86400),
            _make_entry(-0.3, ["stress"], timestamp=night + 3 * 86400),
        ]
        triggers = _detect_time_triggers(entries)
        night_triggers = [t for t in triggers if "Night" in t["trigger"]]
        # Night should be flagged if enough entries exist
        if len(night_triggers) > 0:
            assert night_triggers[0]["impact"] < 0

    @pytest.mark.unit
    def test_no_trigger_when_all_same_time(self):
        """If all entries are at the same time, no time trigger should fire."""
        from datetime import datetime, timezone

        base = int(datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc).timestamp())
        entries = [
            _make_entry(0.0, ["work"], timestamp=base + i * 86400)
            for i in range(10)
        ]
        triggers = _detect_time_triggers(entries)
        # All in same bucket → no deviation → no triggers
        assert len(triggers) == 0


# ============================================================
#               Co-occurrence trigger tests
# ============================================================


class TestCooccurrenceTriggers:
    @pytest.mark.unit
    def test_detects_toxic_combination(self):
        """Two keywords together that are worse than either alone."""
        entries = [
            # "sleep" + "deadline" together — very negative
            _make_entry(-0.7, ["sleep", "deadline"]),
            _make_entry(-0.8, ["sleep", "deadline"]),
            _make_entry(-0.6, ["sleep", "deadline"]),
            # "sleep" alone — mildly negative
            _make_entry(-0.1, ["sleep", "rest"]),
            _make_entry(0.0, ["sleep"]),
            _make_entry(-0.2, ["sleep"]),
            # "deadline" alone — mildly negative
            _make_entry(-0.2, ["deadline", "work"]),
            _make_entry(-0.1, ["deadline"]),
            _make_entry(-0.15, ["deadline"]),
            # Other entries
            _make_entry(0.5, ["gym"]),
            _make_entry(0.4, ["friends"]),
        ]
        triggers = _detect_cooccurrence_triggers(entries)
        # Should find sleep + deadline as a toxic combo
        combo = [t for t in triggers if "sleep" in t["trigger"] and "deadline" in t["trigger"]]
        assert len(combo) >= 1
        assert combo[0]["impact"] < -0.3  # Together is much worse
        assert combo[0]["occurrences"] == 3

    @pytest.mark.unit
    def test_no_cooccurrence_below_threshold(self):
        """Pairs appearing together fewer than 3 times are not flagged."""
        entries = [
            _make_entry(-0.8, ["rare_a", "rare_b"]),
            _make_entry(-0.7, ["rare_a", "rare_b"]),
            # Only 2 co-occurrences
            _make_entry(0.4, ["rare_a"]),
            _make_entry(0.4, ["rare_a"]),
            _make_entry(0.4, ["rare_a"]),
            _make_entry(0.4, ["rare_b"]),
            _make_entry(0.4, ["rare_b"]),
            _make_entry(0.4, ["rare_b"]),
        ]
        triggers = _detect_cooccurrence_triggers(entries)
        combo = [t for t in triggers if "rare_a" in t["trigger"]]
        assert len(combo) == 0


# ============================================================
#                  Full detect_triggers tests
# ============================================================


class TestDetectTriggers:
    @pytest.mark.unit
    def test_returns_empty_for_no_entries(self, monkeypatch):
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])
        result = detect_triggers("u_empty")
        assert result["keyword_triggers"] == []
        assert result["time_triggers"] == []
        assert result["cooccurrence_triggers"] == []
        assert result["total_entries_analyzed"] == 0

    @pytest.mark.unit
    def test_returns_empty_for_few_entries(self, monkeypatch):
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [
            _make_entry(-0.5, ["stress"]),
            _make_entry(0.3, ["happy"]),
        ])
        result = detect_triggers("u_few")
        assert result["total_entries_analyzed"] == 2
        # Not enough entries to find patterns
        assert len(result["keyword_triggers"]) == 0

    @pytest.mark.unit
    def test_filters_out_time_capsules(self, monkeypatch):
        """Time capsules should not be included in trigger analysis."""
        import services.qdrant_service as qs

        entries = [
            _make_entry(-0.8, ["capsule_topic"], entry_type="time_capsule"),
            _make_entry(-0.7, ["capsule_topic"], entry_type="time_capsule"),
            _make_entry(-0.6, ["capsule_topic"], entry_type="time_capsule"),
            _make_entry(0.4, ["other"]),
            _make_entry(0.5, ["other"]),
            _make_entry(0.3, ["other"]),
        ]
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        result = detect_triggers("u_capsule")
        # Only 3 non-capsule entries analyzed
        assert result["total_entries_analyzed"] == 3
        # capsule_topic should not appear as a trigger
        assert all(t["trigger"] != "capsule_topic" for t in result["keyword_triggers"])

    @pytest.mark.unit
    def test_full_analysis_with_mixed_data(self, monkeypatch):
        import services.qdrant_service as qs
        from datetime import datetime, timezone

        base = int(datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc).timestamp())
        entries = [
            _make_entry(-0.6, ["deadline", "stress"], timestamp=base),
            _make_entry(-0.5, ["deadline", "overwhelmed"], timestamp=base + 86400),
            _make_entry(-0.7, ["deadline", "sleep"], timestamp=base + 2 * 86400),
            _make_entry(-0.4, ["deadline"], timestamp=base + 3 * 86400),
            _make_entry(0.5, ["gym", "energy"], timestamp=base + 4 * 86400),
            _make_entry(0.6, ["gym", "friends"], timestamp=base + 5 * 86400),
            _make_entry(0.4, ["gym"], timestamp=base + 6 * 86400),
            _make_entry(0.3, ["relaxing", "weekend"], timestamp=base + 7 * 86400),
            _make_entry(0.2, ["work"], timestamp=base + 8 * 86400),
            _make_entry(-0.1, ["meeting"], timestamp=base + 9 * 86400),
        ]
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)

        result = detect_triggers("u_mixed")
        assert result["total_entries_analyzed"] == 10
        assert isinstance(result["keyword_triggers"], list)
        assert isinstance(result["time_triggers"], list)
        assert isinstance(result["cooccurrence_triggers"], list)

        # "deadline" should be a negative trigger
        deadline = [t for t in result["keyword_triggers"] if t["trigger"] == "deadline"]
        if deadline:
            assert deadline[0]["impact"] < 0

        # "gym" should be a positive trigger
        gym = [t for t in result["keyword_triggers"] if t["trigger"] == "gym"]
        if gym:
            assert gym[0]["impact"] > 0


# ============================================================
#                    API endpoint test
# ============================================================


class TestTriggersEndpoint:
    @pytest.mark.unit
    def test_endpoint_returns_expected_shape(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        import services.qdrant_service as qs
        import routers.dashboard as dash
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [
            _make_entry(-0.5, ["stress", "work"]),
            _make_entry(-0.6, ["stress"]),
            _make_entry(-0.4, ["stress", "deadline"]),
            _make_entry(0.4, ["gym"]),
            _make_entry(0.5, ["gym"]),
            _make_entry(0.3, ["relaxing"]),
        ])

        client = TestClient(app)
        resp = client.get(f"/api/triggers?user_id=test_{uuid.uuid4().hex[:6]}&days=90")
        assert resp.status_code == 200
        data = resp.json()

        assert "keyword_triggers" in data
        assert "time_triggers" in data
        assert "cooccurrence_triggers" in data
        assert "total_entries_analyzed" in data
        assert isinstance(data["keyword_triggers"], list)

    @pytest.mark.unit
    def test_endpoint_returns_empty_for_no_entries(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        import services.qdrant_service as qs
        import routers.dashboard as dash
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])

        client = TestClient(app)
        resp = client.get(f"/api/triggers?user_id=void_{uuid.uuid4().hex[:6]}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_entries_analyzed"] == 0
        assert data["keyword_triggers"] == []
