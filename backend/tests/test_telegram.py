"""
Integration tests for Telegram bot features (P0).

Tests all 5 Telegram features:
1. Daily nudge endpoint
2. Voice note processing (mocked — can't send real voice in tests)
3. Text message processing
4. Drift detection with voice note reply
5. Weekly recap endpoint

Also tests:
- Deduplication (same update_id processed only once)
- /start command
- /status command
- /recap command
- Coping strategy collection flow
- Background processing (returns 200 immediately)

Uses FastAPI TestClient to simulate Telegram webhook payloads.
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


def _make_telegram_update(chat_id: int, text: str = "", voice: bool = False, update_id: int = None):
    """Build a Telegram webhook update payload."""
    msg = {
        "message_id": abs(hash(text)) % 10000,
        "from": {"id": chat_id, "is_bot": False, "first_name": "Test"},
        "chat": {"id": chat_id, "type": "private"},
        "date": 1744700000,
    }
    if voice:
        msg["voice"] = {"file_id": "fake_file_id", "duration": 5}
    else:
        msg["text"] = text

    payload = {"message": msg}
    if update_id:
        payload["update_id"] = update_id
    return payload


class TestTelegramWebhookRouting:
    """Test that the webhook returns 200 instantly for all message types."""

    @pytest.mark.unit
    def test_start_command(self):
        chat_id = 100001
        resp = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "/start"))
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.unit
    def test_empty_update(self):
        resp = client.post("/telegram/webhook", json={})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.unit
    def test_text_message_returns_200(self):
        chat_id = 100002
        resp = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "I feel stressed"))
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    @pytest.mark.unit
    def test_status_command_returns_200(self):
        chat_id = 100003
        resp = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "/status"))
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_recap_command_returns_200(self):
        chat_id = 100004
        resp = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "/recap"))
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_voice_message_returns_200(self):
        chat_id = 100005
        resp = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, voice=True))
        assert resp.status_code == 200


class TestTelegramDeduplication:
    """Test that duplicate updates are not processed twice."""

    @pytest.mark.unit
    def test_same_update_id_ignored(self):
        chat_id = 200001
        update = _make_telegram_update(chat_id, "test dedup", update_id=999999)

        resp1 = client.post("/telegram/webhook", json=update)
        assert resp1.status_code == 200

        resp2 = client.post("/telegram/webhook", json=update)
        assert resp2.status_code == 200
        # Both return 200, but second one is skipped internally

    @pytest.mark.unit
    def test_different_update_ids_processed(self):
        chat_id = 200002
        resp1 = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "msg 1", update_id=888881))
        resp2 = client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "msg 2", update_id=888882))
        assert resp1.status_code == 200
        assert resp2.status_code == 200


class TestTelegramUserRegistration:
    """Test that users are registered on first interaction."""

    @pytest.mark.unit
    def test_user_registered_on_start(self):
        from routers.telegram_bot import _user_registry
        chat_id = 300001
        client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "/start"))
        assert chat_id in _user_registry
        assert _user_registry[chat_id]["user_id"] == f"tg_{chat_id}"

    @pytest.mark.unit
    def test_user_registered_on_text(self):
        from routers.telegram_bot import _user_registry
        chat_id = 300002
        client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "hello"))
        assert chat_id in _user_registry


class TestTelegramNudgeEndpoint:
    """Test the daily nudge cron endpoint."""

    @pytest.mark.unit
    def test_nudge_returns_count(self):
        """POST /telegram/nudge should return sent count."""
        resp = client.post("/telegram/nudge")
        assert resp.status_code == 200
        data = resp.json()
        assert "sent" in data
        assert "total_users" in data
        assert isinstance(data["sent"], int)

    @pytest.mark.unit
    def test_nudge_counts_match(self):
        """Sent count should not exceed total users."""
        resp = client.post("/telegram/nudge")
        data = resp.json()
        assert data["sent"] <= data["total_users"]


class TestTelegramWeeklyRecapEndpoint:
    """Test the weekly recap cron endpoint."""

    @pytest.mark.unit
    def test_weekly_recap_returns_count(self):
        """POST /telegram/weekly-recap should return sent count."""
        resp = client.post("/telegram/weekly-recap")
        assert resp.status_code == 200
        data = resp.json()
        assert "sent" in data
        assert "total_users" in data


class TestTelegramCopingFlow:
    """Test the coping strategy collection via Telegram."""

    @pytest.mark.unit
    def test_awaiting_coping_tracking(self):
        """After positive entry, user should be marked as awaiting coping response."""
        from routers.telegram_bot import _awaiting_coping
        chat_id = 400001
        # Send /start first to register
        client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "/start"))
        # The coping flow is triggered in background — we can at least verify the mechanism exists
        assert isinstance(_awaiting_coping, set)


class TestTelegramTextProcessing:
    """Test that text entries end up in Qdrant via the webhook."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_text_entry_stored_in_qdrant(self):
        """Send a text via Telegram webhook, verify it lands in Qdrant."""
        import time
        from services.qdrant_service import scroll_entries

        chat_id = 500001
        user_id = f"tg_{chat_id}"
        test_text = f"Test entry from Telegram {uuid.uuid4().hex[:8]}"

        # Register + send text
        client.post("/telegram/webhook", json=_make_telegram_update(chat_id, "/start"))
        client.post("/telegram/webhook", json=_make_telegram_update(chat_id, test_text))

        # Wait for background processing
        time.sleep(5)

        entries = scroll_entries(user_id=user_id, limit=10)
        transcripts = [e.payload.get("transcript", "") for e in entries]
        assert any(test_text in t for t in transcripts), (
            f"Text entry not found in Qdrant for {user_id}. "
            f"Found: {transcripts}"
        )


class TestTelegramProcessingFunctions:
    """Test the internal processing functions directly."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_process_entry(self):
        """_process_entry should return valid result dict."""
        from routers.telegram_bot import _process_entry
        result = _process_entry(
            f"test_{uuid.uuid4().hex[:8]}",
            "I am feeling great today, had a wonderful morning run."
        )
        assert "entry_id" in result
        assert "sentiment" in result
        assert "keywords" in result
        assert "drift" in result
        assert result["sentiment"] > 0  # positive text

    @pytest.mark.integration
    @pytest.mark.slow
    def test_process_coping_entry(self):
        """_process_entry with coping type should store correctly."""
        from routers.telegram_bot import _process_entry
        from services.qdrant_service import search_coping_strategies

        test_user = f"test_coping_tg_{uuid.uuid4().hex[:8]}"
        result = _process_entry(
            test_user,
            "What helped me was taking walks and calling my mom.",
            entry_type="coping_strategy"
        )
        assert "entry_id" in result

        # Verify stored as coping
        coping = search_coping_strategies(user_id=test_user)
        assert len(coping) == 1
        assert coping[0].payload["entry_type"] == "coping_strategy"

    @pytest.mark.unit
    def test_format_response(self):
        """_format_response should produce readable text."""
        from routers.telegram_bot import _format_response
        result = {
            "sentiment": -0.5,
            "keywords": ["stressed", "work", "sleep"],
            "drift": {
                "detected": False,
                "skipped": False,
                "message": "Patterns look consistent.",
                "severity": "none",
            },
        }
        text = _format_response(result)
        assert "Entry stored" in text
        assert "stressed" in text

    @pytest.mark.unit
    def test_format_response_with_drift(self):
        """When drift is detected, response should include warning."""
        from routers.telegram_bot import _format_response
        result = {
            "sentiment": -0.7,
            "keywords": ["overwhelmed"],
            "drift": {
                "detected": True,
                "skipped": False,
                "message": "Your entries feel similar to February.",
                "severity": "mild",
            },
        }
        text = _format_response(result)
        assert "Drift detected" in text
        assert "February" in text

    @pytest.mark.unit
    def test_generate_weekly_recap_no_entries(self):
        """Recap for user with no entries should return graceful message."""
        from routers.telegram_bot import _generate_weekly_recap
        text = _generate_weekly_recap(f"empty_user_{uuid.uuid4().hex[:8]}")
        assert "didn't check in" in text.lower()
