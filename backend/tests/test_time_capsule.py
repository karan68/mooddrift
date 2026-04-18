"""
End-to-end tests for the Voice Time Capsule feature (FEATURES.md Feature 2).

Covers:
  - Audio file storage + retrieval (save, path lookup, delete)
  - Capsule readiness detection (positive streak, already-has-recent guard)
  - Capsule storage in Qdrant (entry_type=time_capsule)
  - Capsule retrieval (find_capsules_for_drift, get_capsule_for_playback)
  - API endpoints (POST, GET list, GET ready, GET playback, GET audio stream)
  - Telegram integration (capsule prompt after positive streak, playback on drift)
  - Dashboard voice-entry flow (capsule in response when drift detected)
"""

import io
import os
import sys
import uuid
import time

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.time_capsule import (
    save_capsule_audio,
    get_capsule_audio_path,
    delete_capsule_audio,
    check_capsule_ready,
    store_capsule,
    find_capsules_for_drift,
    get_capsule_for_playback,
    _CAPSULES_DIR,
)


# ============================================================
#                   Audio file I/O tests
# ============================================================


class TestCapsuleAudioIO:
    @pytest.mark.unit
    def test_save_and_retrieve(self):
        data = b"fake audio bytes for testing"
        filename = save_capsule_audio(data, extension="webm")
        assert filename.endswith(".webm")
        path = get_capsule_audio_path(filename)
        assert path is not None
        assert path.read_bytes() == data
        # Cleanup
        delete_capsule_audio(filename)

    @pytest.mark.unit
    def test_get_path_returns_none_for_missing(self):
        assert get_capsule_audio_path("nonexistent_file_12345.webm") is None

    @pytest.mark.unit
    def test_delete_removes_file(self):
        data = b"to be deleted"
        filename = save_capsule_audio(data)
        assert get_capsule_audio_path(filename) is not None
        assert delete_capsule_audio(filename) is True
        assert get_capsule_audio_path(filename) is None

    @pytest.mark.unit
    def test_delete_nonexistent_returns_false(self):
        assert delete_capsule_audio("no_such_file.mp3") is False

    @pytest.mark.unit
    def test_capsules_dir_created(self):
        """Saving a file should auto-create the capsules directory."""
        filename = save_capsule_audio(b"test")
        assert _CAPSULES_DIR.is_dir()
        delete_capsule_audio(filename)


# ============================================================
#                 Capsule readiness tests
# ============================================================


class FakePoint:
    """Minimal stand-in for a Qdrant ScoredPoint."""
    def __init__(self, payload):
        self.payload = payload
        self.id = str(uuid.uuid4())
        self.vector = [0.0] * 384


class TestCheckCapsuleReady:
    @pytest.mark.unit
    def test_not_ready_with_no_entries(self, monkeypatch):
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])
        result = check_capsule_ready("u_empty")
        assert result["ready"] is False
        assert result["streak"] == 0

    @pytest.mark.unit
    def test_not_ready_with_short_streak(self, monkeypatch):
        """3 positive entries < threshold of 5."""
        now_ts = int(time.time())
        points = [
            FakePoint({"sentiment_score": 0.5, "timestamp": now_ts - i * 86400})
            for i in range(3)
        ] + [FakePoint({"sentiment_score": -0.2, "timestamp": now_ts - 4 * 86400})]

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)
        result = check_capsule_ready("u_short")
        assert result["ready"] is False
        assert result["streak"] == 3

    @pytest.mark.unit
    def test_ready_with_5_positive_entries(self, monkeypatch):
        now_ts = int(time.time())
        points = [
            FakePoint({
                "sentiment_score": 0.4 + 0.05 * i,
                "timestamp": now_ts - i * 86400,
                "entry_type": "checkin",
            })
            for i in range(6)
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)
        result = check_capsule_ready("u_ready")
        assert result["ready"] is True
        assert result["streak"] >= 5
        assert result["message"] is not None
        assert "good days" in result["message"].lower() or "positive" in result["message"].lower()

    @pytest.mark.unit
    def test_not_ready_if_recent_capsule_exists(self, monkeypatch):
        """Even with a 5+ streak, don't prompt if they recorded one recently."""
        now_ts = int(time.time())
        # 6 positive entries, one of which is a time_capsule from yesterday
        points = [
            FakePoint({
                "sentiment_score": 0.5,
                "timestamp": now_ts - i * 86400,
                "entry_type": "time_capsule" if i == 1 else "checkin",
            })
            for i in range(6)
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)
        result = check_capsule_ready("u_already")
        assert result["ready"] is False
        assert result["already_has_recent"] is True


# ============================================================
#               Capsule storage + retrieval tests
# ============================================================


class TestStoreCapsule:
    @pytest.mark.unit
    def test_store_creates_qdrant_entry(self, monkeypatch):
        stored = {}

        def fake_upsert(vector, payload):
            pid = str(uuid.uuid4())
            stored["payload"] = payload
            stored["vector"] = vector
            return pid

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "upsert_entry", fake_upsert)

        point_id = store_capsule(
            user_id="u_store",
            transcript="Hey future me, you got this!",
            audio_filename="abc123.webm",
            sentiment=0.7,
            vector=[0.1] * 384,
        )
        assert point_id is not None
        assert stored["payload"]["entry_type"] == "time_capsule"
        assert stored["payload"]["audio_filename"] == "abc123.webm"
        assert stored["payload"]["sentiment_at_recording"] == 0.7
        assert stored["payload"]["user_id"] == "u_store"
        assert "you got this" in stored["payload"]["transcript"]


class TestFindCapsules:
    @pytest.mark.unit
    def test_finds_only_time_capsule_entries(self, monkeypatch):
        now_ts = int(time.time())
        points = [
            FakePoint({
                "entry_type": "checkin",
                "timestamp": now_ts - 86400,
                "transcript": "normal entry",
                "date": "2026-04-10",
                "sentiment_at_recording": 0.2,
                "keywords": [],
            }),
            FakePoint({
                "entry_type": "time_capsule",
                "timestamp": now_ts - 2 * 86400,
                "transcript": "hey future me",
                "date": "2026-04-09",
                "audio_filename": "capsule1.webm",
                "sentiment_at_recording": 0.8,
                "keywords": ["hope"],
            }),
            FakePoint({
                "entry_type": "time_capsule",
                "timestamp": now_ts - 10 * 86400,
                "transcript": "stay strong",
                "date": "2026-04-01",
                "audio_filename": None,
                "sentiment_at_recording": 0.5,
                "keywords": ["strength"],
            }),
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)

        capsules = find_capsules_for_drift("u_find")
        assert len(capsules) == 2
        # Most recent first
        assert capsules[0]["transcript"] == "hey future me"
        assert capsules[0]["has_audio"] is True
        assert capsules[1]["has_audio"] is False

    @pytest.mark.unit
    def test_returns_empty_when_no_capsules(self, monkeypatch):
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])
        assert find_capsules_for_drift("u_none") == []


class TestGetCapsuleForPlayback:
    @pytest.mark.unit
    def test_picks_most_recent_with_audio(self, monkeypatch):
        now_ts = int(time.time())
        points = [
            FakePoint({
                "entry_type": "time_capsule",
                "timestamp": now_ts - 86400,
                "transcript": "recent no audio",
                "date": "2026-04-16",
                "audio_filename": None,
                "sentiment_at_recording": 0.6,
                "keywords": [],
            }),
            FakePoint({
                "entry_type": "time_capsule",
                "timestamp": now_ts - 3 * 86400,
                "transcript": "older with audio",
                "date": "2026-04-14",
                "audio_filename": "old_capsule.webm",
                "sentiment_at_recording": 0.7,
                "keywords": [],
            }),
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)

        capsule = get_capsule_for_playback("u_play")
        assert capsule is not None
        assert capsule["audio_filename"] == "old_capsule.webm"

    @pytest.mark.unit
    def test_returns_text_capsule_if_no_audio(self, monkeypatch):
        now_ts = int(time.time())
        points = [
            FakePoint({
                "entry_type": "time_capsule",
                "timestamp": now_ts - 86400,
                "transcript": "text only capsule",
                "date": "2026-04-16",
                "audio_filename": None,
                "sentiment_at_recording": 0.6,
                "keywords": [],
            }),
        ]
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: points)

        capsule = get_capsule_for_playback("u_textonly")
        assert capsule is not None
        assert capsule["has_audio"] is False
        assert "text only" in capsule["transcript"]

    @pytest.mark.unit
    def test_returns_none_when_no_capsules(self, monkeypatch):
        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])
        assert get_capsule_for_playback("u_empty") is None


# ============================================================
#                    API endpoint tests
# ============================================================


class TestTimeCapsuleEndpoints:
    @pytest.mark.unit
    def test_list_capsules_empty(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        import services.qdrant_service as qs
        import routers.dashboard as dash
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])

        client = TestClient(app)
        resp = client.get(f"/api/time-capsules?user_id=void_{uuid.uuid4().hex[:6]}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["capsules"] == []
        assert data["total"] == 0
        assert "capsule_ready" in data
        assert data["capsule_ready"]["ready"] is False

    @pytest.mark.unit
    def test_capsule_ready_endpoint(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])

        client = TestClient(app)
        resp = client.get(f"/api/time-capsule/ready?user_id=test_{uuid.uuid4().hex[:6]}")
        assert resp.status_code == 200
        data = resp.json()
        assert "ready" in data
        assert "streak" in data

    @pytest.mark.unit
    def test_capsule_playback_endpoint_no_capsules(self, monkeypatch):
        from fastapi.testclient import TestClient
        from main import app

        import services.qdrant_service as qs
        monkeypatch.setattr(qs, "scroll_entries", lambda **kw: [])

        client = TestClient(app)
        resp = client.get(f"/api/time-capsule/playback?user_id=void_{uuid.uuid4().hex[:6]}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["capsule"] is None

    @pytest.mark.unit
    def test_audio_stream_404_for_missing(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.get("/api/time-capsule/nonexistent_file.webm/audio")
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_audio_stream_serves_file(self):
        from fastapi.testclient import TestClient
        from main import app

        # Write a test file
        audio_data = b"fake audio data for streaming test"
        filename = save_capsule_audio(audio_data, extension="webm")

        client = TestClient(app)
        resp = client.get(f"/api/time-capsule/{filename}/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/webm"
        assert resp.content == audio_data

        # Cleanup
        delete_capsule_audio(filename)


# ============================================================
#          Telegram integration tests
# ============================================================


class TestTelegramCapsuleIntegration:
    def _setup_fakes(self, monkeypatch):
        messages = []
        voices = []

        def fake_send_message(chat_id, text):
            messages.append(text)

        def fake_send_voice(chat_id, audio_bytes):
            voices.append(audio_bytes)

        import services.embedding as emb
        import services.sentiment as sent
        import services.keywords as kw
        import services.qdrant_service as qs
        import services.drift_engine as de
        import services.voice_biomarkers as vbm
        import routers.telegram_bot as tb

        monkeypatch.setattr(tb, "_send_message_sync", fake_send_message)
        monkeypatch.setattr(tb, "_send_voice_sync", fake_send_voice)
        monkeypatch.setattr(emb, "generate_embedding", lambda t: [0.0] * 384)
        monkeypatch.setattr(kw, "extract_keywords", lambda t, max_keywords=5: ["happy"])
        monkeypatch.setattr(qs, "upsert_entry", lambda v, p: str(uuid.uuid4()))
        monkeypatch.setattr(vbm, "compute_user_baseline", lambda uid, days=60: None)

        return messages, voices

    @pytest.mark.unit
    def test_capsule_prompt_on_positive_streak(self, monkeypatch):
        """After 5+ positive entries, the bot should prompt for a capsule."""
        messages, _ = self._setup_fakes(monkeypatch)
        import routers.telegram_bot as tb
        import services.sentiment as sent
        import services.drift_engine as de

        # Positive sentiment, no drift
        monkeypatch.setattr(sent, "analyze_sentiment", lambda t: 0.6)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": False, "skipped": False, "drift_score": 0.1,
            "severity": "none", "message": "Stable.",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "stable",
        })
        monkeypatch.setattr(tb, "detect_drift", de.detect_drift)

        # Capsule readiness returns ready=True
        import services.time_capsule as tc
        monkeypatch.setattr(tc, "check_capsule_ready", lambda uid: {
            "ready": True, "streak": 6, "avg_sentiment": 0.55,
            "message": "6 good days!", "already_has_recent": False,
        })

        tb._handle_text_bg(12345, "user_capsule_test", "I feel great today!")

        # Should have sent the capsule prompt
        capsule_prompts = [m for m in messages if "time capsule" in m.lower()]
        assert len(capsule_prompts) >= 1

    @pytest.mark.unit
    def test_capsule_recording_saves(self, monkeypatch):
        """When user is in _awaiting_capsule and sends text, it saves as capsule."""
        messages, _ = self._setup_fakes(monkeypatch)
        import routers.telegram_bot as tb
        import services.sentiment as sent

        monkeypatch.setattr(sent, "analyze_sentiment", lambda t: 0.8)

        stored_capsules = []
        import services.time_capsule as tc
        original_store = tc.store_capsule
        monkeypatch.setattr(tc, "store_capsule", lambda *a, **kw: stored_capsules.append(a) or "fake_id")

        # Simulate: user was prompted
        tb._awaiting_capsule.add(99999)

        tb._handle_text_bg(99999, "user_capsule_save", "Hey future me, things are good right now!")

        # Should have saved it
        assert len(stored_capsules) == 1
        assert "future me" in stored_capsules[0][1]  # transcript

        # Should confirm
        confirm_msgs = [m for m in messages if "saved" in m.lower()]
        assert len(confirm_msgs) >= 1

        # Should no longer be awaiting
        assert 99999 not in tb._awaiting_capsule

    @pytest.mark.unit
    def test_capsule_playback_on_drift(self, monkeypatch):
        """When drift is detected and a capsule exists, play it back."""
        messages, voices = self._setup_fakes(monkeypatch)
        import routers.telegram_bot as tb
        import services.sentiment as sent
        import services.drift_engine as de

        monkeypatch.setattr(sent, "analyze_sentiment", lambda t: -0.5)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": True, "skipped": False, "drift_score": 0.35,
            "severity": "mild", "message": "I see a shift.",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "declining",
        })
        monkeypatch.setattr(tb, "detect_drift", de.detect_drift)

        # TTS returns fake audio
        monkeypatch.setattr(tb, "_generate_voice_insight", lambda d: b"tts_audio")

        # Capsule exists for playback
        import services.time_capsule as tc
        monkeypatch.setattr(tc, "get_capsule_for_playback", lambda uid: {
            "id": "cap1", "date": "2026-03-15",
            "transcript": "You got through February. You'll get through this too.",
            "sentiment_at_recording": 0.7,
            "audio_filename": None, "has_audio": False,
            "keywords": ["strength"],
        })

        tb._handle_text_bg(77777, "user_drift_capsule", "Everything feels heavy")

        # Should mention the capsule
        capsule_msgs = [m for m in messages if "message from you" in m.lower() or "you got through" in m.lower()]
        assert len(capsule_msgs) >= 1

    @pytest.mark.unit
    def test_no_capsule_playback_when_none_exist(self, monkeypatch):
        """When drift detected but no capsules, just show normal drift message."""
        messages, _ = self._setup_fakes(monkeypatch)
        import routers.telegram_bot as tb
        import services.sentiment as sent
        import services.drift_engine as de

        monkeypatch.setattr(sent, "analyze_sentiment", lambda t: -0.4)
        monkeypatch.setattr(de, "detect_drift", lambda *a, **kw: {
            "detected": True, "skipped": False, "drift_score": 0.3,
            "severity": "mild", "message": "Subtle shift.",
            "matching_period": None, "matching_context": None,
            "coping_strategies": None, "sentiment_direction": "declining",
        })
        monkeypatch.setattr(tb, "detect_drift", de.detect_drift)
        monkeypatch.setattr(tb, "_generate_voice_insight", lambda d: None)

        import services.time_capsule as tc
        monkeypatch.setattr(tc, "get_capsule_for_playback", lambda uid: None)

        tb._handle_text_bg(88888, "user_no_capsule", "Bad day")

        # No capsule-related messages
        capsule_msgs = [m for m in messages if "message from you" in m.lower()]
        assert len(capsule_msgs) == 0
