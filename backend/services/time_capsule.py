"""
Voice Time Capsule — FEATURES.md Feature 2.

During good periods (sentiment > 0.3 sustained for 5+ days), prompt the user
to record a message to their future self.  When drift is later detected, find
matching capsules from positive periods and surface them.

Key concepts:
  - "Capsule-ready" detection:  check if the last N entries are all positive
  - Audio storage:  raw bytes written to backend/capsules/<uuid>.webm
  - Qdrant entry:  entry_type="time_capsule" with audio_path in payload
  - Retrieval on drift:  search capsules whose recording date falls in or
    near a historically positive window
  - Playback:  served via GET /api/time-capsule/<id>/audio
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# Directory where capsule audio files are stored.
_CAPSULES_DIR = Path(__file__).resolve().parent.parent / "capsules"

# How many consecutive positive entries before prompting a capsule recording.
_POSITIVE_STREAK_THRESHOLD = 5

# Minimum sentiment score to count as "positive".
_POSITIVE_SENTIMENT = 0.3


def _ensure_capsules_dir() -> Path:
    """Create the capsules directory if it doesn't exist."""
    _CAPSULES_DIR.mkdir(parents=True, exist_ok=True)
    return _CAPSULES_DIR


def save_capsule_audio(audio_bytes: bytes, extension: str = "webm") -> str:
    """Write raw audio bytes to disk.  Returns the filename (not full path)."""
    _ensure_capsules_dir()
    filename = f"{uuid.uuid4().hex}.{extension}"
    filepath = _CAPSULES_DIR / filename
    filepath.write_bytes(audio_bytes)
    return filename


def get_capsule_audio_path(filename: str) -> Optional[Path]:
    """Return the full path for a capsule audio file, or None if missing."""
    path = _CAPSULES_DIR / filename
    return path if path.is_file() else None


def delete_capsule_audio(filename: str) -> bool:
    """Remove a capsule audio file from disk."""
    path = _CAPSULES_DIR / filename
    if path.is_file():
        path.unlink()
        return True
    return False


def check_capsule_ready(user_id: str) -> dict:
    """Check whether the user is in a sustained positive period and should be
    prompted to record a time capsule.

    Returns:
        {
          "ready": bool,
          "streak": int,         # consecutive positive entries
          "avg_sentiment": float, # avg sentiment over the streak
          "message": str | None,  # prompt message if ready
          "already_has_recent": bool,  # True if they recorded one in last 7 days
        }
    """
    from services.qdrant_service import scroll_entries

    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=14)).timestamp())
    entries = scroll_entries(user_id=user_id, date_from=date_from, limit=30)

    if not entries:
        return {"ready": False, "streak": 0, "avg_sentiment": 0.0,
                "message": None, "already_has_recent": False}

    # Sort by timestamp descending (most recent first)
    entries.sort(
        key=lambda e: e.payload.get("timestamp", 0), reverse=True,
    )

    # Count consecutive positive entries from most recent
    streak = 0
    sentiment_sum = 0.0
    for e in entries:
        s = e.payload.get("sentiment_score", 0.0)
        if s >= _POSITIVE_SENTIMENT:
            streak += 1
            sentiment_sum += s
        else:
            break

    avg_sentiment = sentiment_sum / streak if streak > 0 else 0.0

    # Check if user already recorded a capsule in the last 7 days
    week_ago = int((now - timedelta(days=7)).timestamp())
    recent_capsules = scroll_entries(
        user_id=user_id, date_from=week_ago, limit=5,
    )
    already_has_recent = any(
        e.payload.get("entry_type") == "time_capsule"
        for e in recent_capsules
    )

    ready = streak >= _POSITIVE_STREAK_THRESHOLD and not already_has_recent

    message = None
    if ready:
        message = (
            f"You've had {streak} positive check-ins in a row. "
            "Want to record a message to your future self? "
            "Something you'd want to hear on a tough day."
        )

    return {
        "ready": ready,
        "streak": streak,
        "avg_sentiment": round(avg_sentiment, 3),
        "message": message,
        "already_has_recent": already_has_recent,
    }


def store_capsule(
    user_id: str,
    transcript: str,
    audio_filename: Optional[str],
    sentiment: float,
    vector: list[float],
    open_date: Optional[str] = None,
) -> str:
    """Store a time capsule entry in Qdrant.

    Args:
        user_id: User who recorded it.
        transcript: What they said (transcribed).
        audio_filename: Filename of the audio file in capsules/ dir, or None.
        sentiment: Sentiment score at time of recording.
        vector: Embedding vector of the transcript.
        open_date: Optional date string (YYYY-MM-DD) when capsule should open.
                   If None, capsule is available immediately (opened on drift).

    Returns:
        The Qdrant point ID.
    """
    from services.qdrant_service import upsert_entry
    from services.keywords import extract_keywords

    now = datetime.now(timezone.utc)
    keywords = extract_keywords(transcript)

    payload = {
        "user_id": user_id,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": int(now.timestamp()),
        "transcript": transcript,
        "sentiment_score": sentiment,
        "keywords": keywords,
        "week_number": now.isocalendar()[1],
        "month": now.strftime("%Y-%m"),
        "entry_type": "time_capsule",
        "audio_filename": audio_filename,
        "sentiment_at_recording": sentiment,
        "open_date": open_date,  # None = opens on drift or anytime
    }

    return upsert_entry(vector, payload)


def find_capsules_for_drift(user_id: str, days: int = 120) -> list[dict]:
    """Find all time capsules for a user, sorted by most recent first.

    Used when drift is detected — we surface capsules recorded during
    the user's positive periods so they can hear their own voice from
    a better time.

    Returns a list of dicts with capsule metadata.
    """
    from services.qdrant_service import scroll_entries

    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())
    entries = scroll_entries(user_id=user_id, date_from=date_from, limit=100)

    capsules = []
    for e in entries:
        p = e.payload or {}
        if p.get("entry_type") != "time_capsule":
            continue
        capsules.append({
            "id": str(e.id),
            "date": p.get("date"),
            "timestamp": p.get("timestamp"),
            "transcript": p.get("transcript", ""),
            "sentiment_at_recording": p.get("sentiment_at_recording", 0.0),
            "audio_filename": p.get("audio_filename"),
            "has_audio": bool(p.get("audio_filename")),
            "keywords": p.get("keywords", []),
            "open_date": p.get("open_date"),
        })

    # Sort by timestamp descending (most recent capsule first)
    capsules.sort(key=lambda c: c.get("timestamp", 0), reverse=True)
    return capsules


def get_capsules_opening_today(user_id: str) -> list[dict]:
    """Return capsules whose open_date is today (or earlier and not yet seen).

    Used by the dashboard to show a notification banner.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_capsules = find_capsules_for_drift(user_id, days=365)
    return [
        c for c in all_capsules
        if c.get("open_date") and c["open_date"] <= today
    ]


def get_capsule_for_playback(user_id: str) -> Optional[dict]:
    """Get the best capsule to play back right now during a drift.

    Picks the most recent capsule with audio. Returns None if no capsules
    exist or none have audio.
    """
    capsules = find_capsules_for_drift(user_id, days=180)
    for c in capsules:
        if c.get("has_audio"):
            return c
    # Fallback: return text-only capsule if no audio capsules exist
    return capsules[0] if capsules else None
