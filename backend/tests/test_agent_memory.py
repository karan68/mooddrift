"""
Tests for Agent Memory — FEATURES.md Feature 5.

Covers:
  - build_agent_context with entries (last entry, themes, sentiment trend)
  - build_agent_context with no entries (empty state)
  - build_agent_context with triggers and capsules
  - format_context_for_vapi (natural language output)
  - format_context_for_telegram (context-aware reply additions)
  - /api/context endpoint shape
  - Vapi webhook get_user_context function handler
  - Telegram _format_response with user_id (memory injection)
"""

import os
import sys
import uuid
import time
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.agent_memory import (
    build_agent_context,
    format_context_for_vapi,
    format_context_for_telegram,
)


# ============================================================
#                      Fake data helpers
# ============================================================

class FakePoint:
    def __init__(self, payload):
        self.payload = payload
        self.id = str(uuid.uuid4())
        self.vector = [0.0] * 384


def _make_entry(sentiment, keywords, days_ago=0, transcript="test entry", entry_type="checkin"):
    now = int(time.time())
    from datetime import datetime, timezone, timedelta
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return FakePoint({
        "sentiment_score": sentiment,
        "keywords": keywords,
        "timestamp": now - days_ago * 86400,
        "date": d.strftime("%Y-%m-%d"),
        "transcript": transcript,
        "entry_type": entry_type,
        "week_number": d.isocalendar()[1],
        "month": d.strftime("%Y-%m"),
    })


# ============================================================
#               build_agent_context tests
# ============================================================


class TestBuildAgentContext:
    @pytest.mark.unit
    def test_no_entries_returns_empty_context(self, monkeypatch):
        import services.qdrant_service as qs
        import services.drift_engine as de
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": True, "drift_score": 0,
            "severity": "none", "message": "No data", "matching_period": None,
            "matching_context": None, "coping_strategies": None,
            "sentiment_direction": "stable",
        })

        ctx = build_agent_context("u_empty")
        assert ctx["has_context"] is False
        assert ctx["last_entry"] is None
        assert ctx["entry_count_14d"] == 0

    @pytest.mark.unit
    def test_with_entries_returns_rich_context(self, monkeypatch):
        entries = [
            _make_entry(-0.5, ["stress", "work"], days_ago=0, transcript="Deadlines are crushing me"),
            _make_entry(-0.3, ["stress", "sleep"], days_ago=1, transcript="Can't sleep again"),
            _make_entry(0.2, ["gym", "energy"], days_ago=2, transcript="Went to gym today"),
            _make_entry(-0.4, ["work", "overwhelmed"], days_ago=3, transcript="Work is overwhelming"),
            _make_entry(0.1, ["friends"], days_ago=4, transcript="Talked to friends"),
            _make_entry(0.3, ["weekend"], days_ago=5, transcript="Nice weekend"),
        ]

        import services.qdrant_service as qs
        import services.drift_engine as de
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": True, "skipped": False, "drift_score": 0.3,
            "severity": "mild", "message": "Subtle shift detected.",
            "matching_period": "Feb 10-17", "matching_context": ["work"],
            "coping_strategies": ["Taking weekends off"],
            "sentiment_direction": "declining",
        })

        ctx = build_agent_context("u_rich")
        assert ctx["has_context"] is True
        assert ctx["last_entry"] is not None
        assert "Deadlines" in ctx["last_entry"]["transcript"]
        assert ctx["last_entry"]["sentiment"] == -0.5
        assert len(ctx["recent_themes"]) > 0
        assert ctx["drift_status"] == "mild"
        assert ctx["entry_count_14d"] == 6

    @pytest.mark.unit
    def test_filters_time_capsules(self, monkeypatch):
        entries = [
            _make_entry(0.5, ["happy"], days_ago=0, transcript="Great day"),
            _make_entry(0.8, ["hope"], days_ago=1, transcript="Capsule message", entry_type="time_capsule"),
            _make_entry(0.3, ["okay"], days_ago=2, transcript="Doing okay"),
        ]

        import services.qdrant_service as qs
        import services.drift_engine as de
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "stable",
        })

        ctx = build_agent_context("u_capsule")
        # Time capsule should be filtered out
        assert ctx["entry_count_14d"] == 2
        assert "Capsule" not in ctx["last_entry"]["transcript"]

    @pytest.mark.unit
    def test_detects_recurring_themes(self, monkeypatch):
        entries = [
            _make_entry(-0.5, ["stress", "deadline"], days_ago=0),
            _make_entry(-0.4, ["stress", "deadline"], days_ago=1),
            _make_entry(0.2, ["gym"], days_ago=2),
        ]

        import services.qdrant_service as qs
        import services.drift_engine as de
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "stable",
        })

        ctx = build_agent_context("u_recurring")
        # "stress" and "deadline" appear in both of the last 2 entries
        assert len(ctx.get("recurring_themes", [])) > 0
        assert "stress" in ctx["recurring_themes"] or "deadline" in ctx["recurring_themes"]

    @pytest.mark.unit
    def test_sentiment_trend_improving(self, monkeypatch):
        entries = [
            _make_entry(0.5, ["happy"], days_ago=0),
            _make_entry(0.4, ["good"], days_ago=1),
            _make_entry(-0.3, ["sad"], days_ago=5),
            _make_entry(-0.4, ["bad"], days_ago=6),
        ]

        import services.qdrant_service as qs
        import services.drift_engine as de
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "improving",
        })

        ctx = build_agent_context("u_improving")
        assert ctx["sentiment_trend"] == "improving"


# ============================================================
#              format_context_for_vapi tests
# ============================================================


class TestFormatContextForVapi:
    @pytest.mark.unit
    def test_no_context_returns_new_user_message(self):
        result = format_context_for_vapi({"has_context": False})
        assert "new user" in result.lower() or "no previous" in result.lower()

    @pytest.mark.unit
    def test_with_context_includes_last_entry(self):
        ctx = {
            "has_context": True,
            "last_entry": {
                "date": "2026-04-17",
                "transcript": "I've been stressed about deadlines all week",
                "sentiment": -0.5,
                "keywords": ["stressed", "deadlines"],
            },
            "recent_themes": ["stress", "work"],
            "recurring_themes": ["stress"],
            "sentiment_trend": "declining",
            "trend_detail": "from 0.10 to -0.40",
            "drift_status": "mild",
            "drift_message": "Subtle shift detected.",
            "triggers": [{"word": "deadlines", "impact": -0.5, "type": "negative"}],
            "has_capsule": True,
            "entry_count_14d": 8,
            "avg_sentiment_14d": -0.2,
        }
        result = format_context_for_vapi(ctx)
        assert "2026-04-17" in result
        assert "stressed about deadlines" in result
        assert "declining" in result
        assert "DRIFT DETECTED" in result
        assert "deadlines" in result
        assert "time capsule" in result
        assert "8" in result

    @pytest.mark.unit
    def test_includes_recurring_themes(self):
        ctx = {
            "has_context": True,
            "last_entry": {"date": "2026-04-17", "transcript": "test", "sentiment": 0.0, "keywords": []},
            "recent_themes": [],
            "recurring_themes": ["sleep", "work"],
            "sentiment_trend": "stable",
            "trend_detail": "",
            "drift_status": "stable",
            "drift_message": "",
            "triggers": [],
            "has_capsule": False,
            "entry_count_14d": 3,
            "avg_sentiment_14d": 0.0,
        }
        result = format_context_for_vapi(ctx)
        assert "sleep" in result
        assert "work" in result
        assert "on their mind" in result


# ============================================================
#           format_context_for_telegram tests
# ============================================================


class TestFormatContextForTelegram:
    @pytest.mark.unit
    def test_no_context_returns_none(self):
        assert format_context_for_telegram({"has_context": False}, 0.0) is None

    @pytest.mark.unit
    def test_recurring_themes_mentioned(self):
        ctx = {
            "has_context": True,
            "recurring_themes": ["stress", "sleep"],
            "last_entry": {"sentiment": 0.0},
            "triggers": [],
        }
        result = format_context_for_telegram(ctx, -0.3)
        assert result is not None
        assert "stress" in result

    @pytest.mark.unit
    def test_mood_shift_detected(self):
        ctx = {
            "has_context": True,
            "recurring_themes": [],
            "last_entry": {"sentiment": -0.5},
            "triggers": [],
        }
        # Current sentiment much better than last
        result = format_context_for_telegram(ctx, 0.2)
        assert result is not None
        assert "lighter" in result

    @pytest.mark.unit
    def test_mood_drop_detected(self):
        ctx = {
            "has_context": True,
            "recurring_themes": [],
            "last_entry": {"sentiment": 0.3},
            "triggers": [],
        }
        # Current sentiment much worse
        result = format_context_for_telegram(ctx, -0.4)
        assert result is not None
        assert "heavier" in result.lower() or "here" in result.lower()

    @pytest.mark.unit
    def test_no_noteworthy_change_returns_none(self):
        ctx = {
            "has_context": True,
            "recurring_themes": [],
            "last_entry": {"sentiment": 0.0},
            "triggers": [],
        }
        result = format_context_for_telegram(ctx, 0.05)
        assert result is None


# ============================================================
#                    API endpoint test
# ============================================================


class TestContextEndpoint:
    @pytest.mark.unit
    def test_endpoint_returns_context(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        entries = [
            _make_entry(-0.3, ["work", "stress"], days_ago=0, transcript="Tough day"),
            _make_entry(0.2, ["friends"], days_ago=1, transcript="Saw friends"),
        ]

        import services.qdrant_service as qs
        import services.drift_engine as de
        import routers.dashboard as dash
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "stable",
        })

        client = TestClient(app)
        resp = client.get(f"/api/context?user_id=test_{uuid.uuid4().hex[:6]}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_context"] is True
        assert data["last_entry"] is not None
        assert "sentiment_trend" in data
        assert "drift_status" in data
        assert "entry_count_14d" in data


# ============================================================
#               Vapi webhook integration test
# ============================================================


class TestVapiGetUserContext:
    @pytest.mark.unit
    def test_get_user_context_via_webhook(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        entries = [
            _make_entry(-0.4, ["deadline"], days_ago=0, transcript="Deadlines everywhere"),
            _make_entry(-0.3, ["sleep"], days_ago=1, transcript="Bad sleep"),
        ]

        import services.qdrant_service as qs
        import services.drift_engine as de
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "stable",
        })

        client = TestClient(app)

        # Simulate Vapi tool-calls event with get_user_context
        payload = {
            "message": {
                "type": "tool-calls",
                "toolCallList": [
                    {
                        "id": "call_123",
                        "name": "get_user_context",
                        "parameters": {"user_id": "demo_user"},
                    }
                ],
            }
        }

        resp = client.post("/vapi/webhook", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "get_user_context"

        # The result should be a string with context info
        result_str = data["results"][0]["result"]
        assert isinstance(result_str, str)
        assert "Deadlines" in result_str


# ============================================================
#            Telegram format_response with memory
# ============================================================


class TestTelegramMemoryIntegration:
    @pytest.mark.unit
    def test_format_response_includes_memory_line(self, monkeypatch):
        """When user_id is passed, _format_response should add context-aware text."""
        import services.qdrant_service as qs
        import services.drift_engine as de

        entries = [
            _make_entry(-0.5, ["stress", "work"], days_ago=0, transcript="Very stressed"),
            _make_entry(-0.4, ["stress", "work"], days_ago=1, transcript="Work is hard"),
        ]
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: entries)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "stable",
        })

        from routers.telegram_bot import _format_response

        result = {
            "sentiment": -0.5,
            "keywords": ["stress", "work"],
            "drift": {"detected": False, "skipped": False, "message": "Stable.", "severity": "none"},
            "congruence": None,
        }

        text = _format_response(result, chat_id=None, user_id="demo_user")
        # Should contain a memory line about recurring themes
        assert "stress" in text.lower() or "work" in text.lower()

    @pytest.mark.unit
    def test_format_response_works_without_user_id(self):
        """Backward compat: if no user_id passed, no crash."""
        from routers.telegram_bot import _format_response

        result = {
            "sentiment": 0.3,
            "keywords": ["gym"],
            "drift": {"detected": False, "skipped": False, "message": "Stable.", "severity": "none"},
            "congruence": None,
        }

        text = _format_response(result)
        assert "Entry stored" in text
