"""
Tests for P1 + P2 features:
- Therapist Report API
- Weekly Recap (LLM-generated)
- Trusted Contact Alerts
- Consistency Acknowledgment
"""

import pytest
import json
import uuid

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestTherapistReport:
    """Tests for GET /api/report endpoint."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_returns_200(self):
        resp = client.get("/api/report?days=14")
        assert resp.status_code == 200

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_has_required_sections(self):
        resp = client.get("/api/report?days=90")
        data = resp.json()
        assert "summary" in data
        assert "sentiment_trend" in data
        assert "top_keywords" in data
        assert "key_entries" in data
        assert "drift" in data
        assert "coping_strategies" in data

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_summary_fields(self):
        resp = client.get("/api/report?days=90")
        summary = resp.json()["summary"]
        assert "total_entries" in summary
        assert "avg_sentiment" in summary
        assert "min_sentiment" in summary
        assert "max_sentiment" in summary
        assert "days_with_entries" in summary
        assert summary["total_entries"] > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_key_entries_has_negative_and_positive(self):
        resp = client.get("/api/report?days=90")
        key = resp.json()["key_entries"]
        assert "most_negative" in key
        assert "most_positive" in key
        assert len(key["most_negative"]) > 0
        assert len(key["most_positive"]) > 0

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_negative_entries_have_lower_sentiment(self):
        resp = client.get("/api/report?days=90")
        key = resp.json()["key_entries"]
        neg_scores = [e["sentiment"] for e in key["most_negative"]]
        pos_scores = [e["sentiment"] for e in key["most_positive"]]
        assert max(neg_scores) <= min(pos_scores)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_has_keywords(self):
        resp = client.get("/api/report?days=90")
        keywords = resp.json()["top_keywords"]
        assert len(keywords) > 0
        assert "word" in keywords[0]
        assert "count" in keywords[0]

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_has_drift_info(self):
        resp = client.get("/api/report?days=90")
        drift = resp.json()["drift"]
        assert "detected" in drift
        assert "severity" in drift
        assert "message" in drift

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_nonexistent_user(self):
        resp = client.get(f"/api/report?user_id=nonexistent_{uuid.uuid4().hex[:8]}&days=14")
        assert resp.status_code == 200
        assert "error" in resp.json()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_coping_strategies(self):
        resp = client.get("/api/report?days=90")
        coping = resp.json()["coping_strategies"]
        assert isinstance(coping, list)

    @pytest.mark.integration
    @pytest.mark.slow
    def test_report_sentiment_trend(self):
        resp = client.get("/api/report?days=90")
        trend = resp.json()["sentiment_trend"]
        assert len(trend) > 0
        assert "date" in trend[0]
        assert "avg_sentiment" in trend[0]


class TestTrustedContactAlerts:
    """Tests for trusted contact functionality."""

    @pytest.mark.unit
    def test_trust_command(self):
        chat_id = 600001
        resp = client.post("/telegram/webhook", json={
            "update_id": 600001,
            "message": {
                "message_id": 1,
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1744700000,
                "text": "/trust @myfriend",
            }
        })
        assert resp.status_code == 200

        from routers.telegram_bot import _user_registry
        assert _user_registry[chat_id].get("trusted_enabled") is True
        assert _user_registry[chat_id].get("trusted_contact") == "@myfriend"

    @pytest.mark.unit
    def test_untrust_command(self):
        chat_id = 600002
        # Register + trust first
        client.post("/telegram/webhook", json={
            "update_id": 600002,
            "message": {
                "message_id": 1,
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1744700000,
                "text": "/trust 9876543210",
            }
        })
        # Now untrust
        client.post("/telegram/webhook", json={
            "update_id": 600003,
            "message": {
                "message_id": 2,
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1744700000,
                "text": "/untrust",
            }
        })

        from routers.telegram_bot import _user_registry
        assert _user_registry[chat_id].get("trusted_enabled") is False

    @pytest.mark.unit
    def test_trust_without_contact(self):
        chat_id = 600004
        resp = client.post("/telegram/webhook", json={
            "update_id": 600004,
            "message": {
                "message_id": 1,
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1744700000,
                "text": "/trust",
            }
        })
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_check_trusted_alerts_endpoint(self):
        resp = client.post("/telegram/check-trusted-alerts")
        assert resp.status_code == 200
        assert "alerted" in resp.json()


class TestConsistencyAcknowledgment:
    """Tests for consistency milestone checks."""

    @pytest.mark.unit
    def test_check_consistency_endpoint(self):
        resp = client.post("/telegram/check-consistency")
        assert resp.status_code == 200
        assert "acknowledged" in resp.json()

    @pytest.mark.unit
    def test_milestone_tracking(self):
        from routers.telegram_bot import _user_registry
        chat_id = 700001
        # Register user
        client.post("/telegram/webhook", json={
            "update_id": 700001,
            "message": {
                "message_id": 1,
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1744700000,
                "text": "/start",
            }
        })
        assert chat_id in _user_registry
        assert _user_registry[chat_id].get("last_consistency_milestone", 0) == 0


class TestWeeklyRecapLLM:
    """Tests for the LLM-powered weekly recap."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_recap_generates_text(self):
        from routers.telegram_bot import _generate_weekly_recap
        recap = _generate_weekly_recap("demo_user")
        assert isinstance(recap, str)
        assert len(recap) > 50
        assert "reflection" in recap.lower() or "week" in recap.lower()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_recap_no_entries(self):
        from routers.telegram_bot import _generate_weekly_recap
        recap = _generate_weekly_recap(f"empty_{uuid.uuid4().hex[:8]}")
        assert "didn't check in" in recap.lower()

    @pytest.mark.unit
    def test_recap_endpoint(self):
        resp = client.post("/telegram/weekly-recap")
        assert resp.status_code == 200
        data = resp.json()
        assert "sent" in data
        assert "total_users" in data


class TestLLMSummary:
    """Tests for the Groq LLM summary service."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_generate_summary(self):
        from services.llm_summary import generate_summary
        result = generate_summary("Summarize this week: user checked in 5 times, average mood was negative, they mentioned work stress 3 times.")
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.integration
    @pytest.mark.slow
    def test_generate_summary_not_clinical(self):
        from services.llm_summary import generate_summary
        result = generate_summary("User had 3 entries with avg sentiment -0.5. Top keywords: stress, work.")
        result_lower = result.lower()
        # Should not use clinical terms
        assert "diagnos" not in result_lower
        assert "disorder" not in result_lower


class TestTTS:
    """Tests for the text-to-speech service."""

    @pytest.mark.slow
    @pytest.mark.unit
    def test_text_to_speech_returns_bytes(self):
        from services.tts import text_to_speech
        audio = text_to_speech("Hello, this is a test of the voice synthesis.")
        assert isinstance(audio, bytes)
        assert len(audio) > 1000  # should be at least 1KB of audio

    @pytest.mark.slow
    @pytest.mark.unit
    def test_text_to_speech_empty(self):
        from services.tts import text_to_speech
        audio = text_to_speech("Test.")
        assert isinstance(audio, bytes)
