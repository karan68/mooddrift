"""
Telegram bot webhook handler.

Implements all 5 features from FEATURES.md:
1. Daily nudge at preferred time (via /telegram/nudge cron endpoint)
2. Receive voice notes → transcribe → embed → store → drift check → reply
3. Receive text → embed → store → drift check → reply
4. Send voice summary (TTS) when drift is detected
5. Weekly voice recap (via /telegram/weekly-recap cron endpoint)

Key design: Returns 200 OK to Telegram INSTANTLY, processes in background thread.
This prevents Telegram from retrying and makes the bot feel responsive.
"""

import asyncio
import threading
from datetime import datetime, timezone, timedelta
from collections import Counter

import httpx
from fastapi import APIRouter, Request, BackgroundTasks

from config import settings
from services.qdrant_service import scroll_entries
from services.drift_engine import detect_drift

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

# In-memory user registry (in production, use a DB)
_user_registry: dict[int, dict] = {}

# Dedup: track processed update IDs to prevent double processing
_processed_updates: set[int] = set()
_MAX_PROCESSED = 1000


def _send_message_sync(chat_id: int, text: str):
    """Send a text message (synchronous, for use in background threads)."""
    httpx.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )


def _send_voice_sync(chat_id: int, voice_bytes: bytes):
    """Send a voice note (synchronous, for background threads)."""
    httpx.post(
        f"{TELEGRAM_API}/sendVoice",
        files={"voice": ("insight.mp3", voice_bytes, "audio/mpeg")},
        data={"chat_id": str(chat_id)},
        timeout=30,
    )


def _download_file_sync(file_id: str) -> bytes:
    """Download a file from Telegram (synchronous)."""
    resp = httpx.get(
        f"{TELEGRAM_API}/getFile",
        params={"file_id": file_id},
        timeout=10,
    )
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]

    resp = httpx.get(
        f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}",
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


def _generate_voice_insight(drift: dict) -> bytes | None:
    """Generate a TTS voice note for a drift insight. Returns MP3 bytes or None."""
    if not drift["detected"]:
        return None
    try:
        from services.tts import text_to_speech
        text = drift["message"].replace("*", "").replace("_", "")
        return text_to_speech(text)
    except Exception as e:
        print(f"[telegram] TTS error: {e}")
        return None


def _process_entry(user_id: str, transcript: str, entry_type: str = "checkin") -> dict:
    """Process a journal entry: embed, analyze, store, drift check."""
    from services.embedding import generate_embedding
    from services.sentiment import analyze_sentiment
    from services.keywords import extract_keywords
    from services.qdrant_service import upsert_entry

    vector = generate_embedding(transcript)
    sentiment = analyze_sentiment(transcript)
    keywords = extract_keywords(transcript)

    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": int(now.timestamp()),
        "transcript": transcript,
        "sentiment_score": sentiment,
        "keywords": keywords,
        "week_number": now.isocalendar()[1],
        "month": now.strftime("%Y-%m"),
        "entry_type": entry_type,
    }

    point_id = upsert_entry(vector, payload)
    drift_result = detect_drift(user_id)

    return {
        "entry_id": point_id,
        "sentiment": sentiment,
        "keywords": keywords,
        "drift": drift_result,
    }


# Track users who were asked "what helped?" — awaiting coping response
_awaiting_coping: set[int] = set()


def _format_response(result: dict, chat_id: int | None = None) -> str:
    """Format the processing result into a user-friendly text reply."""
    sentiment = result["sentiment"]
    keywords = result["keywords"]
    drift = result["drift"]

    if sentiment > 0.3:
        mood = "😊"
    elif sentiment > 0:
        mood = "🙂"
    elif sentiment > -0.3:
        mood = "😐"
    else:
        mood = "😔"

    lines = [f"{mood} *Entry stored.*"]
    if keywords:
        lines.append(f"Themes: {', '.join(keywords[:3])}")
    if drift["skipped"]:
        lines.append(f"\n_{drift['message']}_")
    elif drift["detected"]:
        lines.append(f"\n⚠️ *Drift detected* ({drift['severity']})")
        lines.append(drift["message"])
    else:
        lines.append(f"\n✦ {drift['message']}")

    # If sentiment is positive and recent drift was detected, ask what helped
    if sentiment > 0.2 and not drift.get("skipped") and chat_id is not None:
        lines.append(
            "\n💡 _It sounds like things are improving. "
            "What's been helping you feel better? "
            "Reply and I'll remember it for next time._"
        )
        _awaiting_coping.add(chat_id)

    return "\n".join(lines)


def _generate_weekly_recap(user_id: str) -> str:
    """Generate a weekly recap text for a user."""
    now = datetime.now(timezone.utc)
    week_ago = int((now - timedelta(days=7)).timestamp())
    entries = scroll_entries(user_id=user_id, date_from=week_ago, limit=50)

    if not entries:
        return "You didn't check in this week. No worries — I'll be here when you're ready."

    entry_count = len(entries)
    sentiments = [e.payload.get("sentiment_score", 0) for e in entries]
    avg_sentiment = sum(sentiments) / len(sentiments)

    all_keywords: list[str] = []
    for e in entries:
        all_keywords.extend(e.payload.get("keywords", []))
    keyword_counts = Counter(all_keywords)
    top_keywords = [kw for kw, _ in keyword_counts.most_common(3)]

    drift = detect_drift(user_id)

    parts = [f"Here's your weekly reflection."]
    parts.append(f"You checked in {entry_count} times this week.")

    if avg_sentiment > 0.2:
        parts.append("Your overall mood was positive.")
    elif avg_sentiment > -0.2:
        parts.append("Your overall mood was mixed.")
    else:
        parts.append("Your overall mood was lower than usual this week.")

    if top_keywords:
        parts.append(f"You mentioned {', '.join(top_keywords)} most often.")

    if drift["detected"]:
        parts.append(f"Your entries are showing {drift['severity']} drift. {drift['message']}")
    else:
        parts.append("Your patterns look consistent. Keep up the practice.")

    parts.append("Take care of yourself.")
    return " ".join(parts)


# === Background processing functions ===

def _handle_voice_bg(chat_id: int, user_id: str, file_id: str):
    """Process voice note in background thread."""
    try:
        _send_message_sync(chat_id, "🎧 _Listening..._")
        from services.transcription import transcribe_audio

        audio_bytes = _download_file_sync(file_id)
        transcript = transcribe_audio(audio_bytes)

        if not transcript.strip():
            _send_message_sync(chat_id, "I couldn't make out what you said. Try again?")
            return

        result = _process_entry(user_id, transcript)
        _send_message_sync(chat_id, _format_response(result, chat_id))

        if result["drift"]["detected"]:
            voice = _generate_voice_insight(result["drift"])
            if voice:
                _send_voice_sync(chat_id, voice)
    except Exception as e:
        _send_message_sync(chat_id, "Sorry, something went wrong. Try again?")
        print(f"[telegram] voice bg error: {e}")


def _handle_text_bg(chat_id: int, user_id: str, text: str):
    """Process text message in background thread."""
    try:
        # Check if this is a coping strategy response
        if chat_id in _awaiting_coping:
            _awaiting_coping.discard(chat_id)
            _process_entry(user_id, text, entry_type="coping_strategy")
            _send_message_sync(
                chat_id,
                "✅ *Coping strategy saved.* I'll remind you of this "
                "if I notice a similar pattern in the future."
            )
            return

        result = _process_entry(user_id, text)
        _send_message_sync(chat_id, _format_response(result, chat_id))

        if result["drift"]["detected"]:
            voice = _generate_voice_insight(result["drift"])
            if voice:
                _send_voice_sync(chat_id, voice)
    except Exception as e:
        _send_message_sync(chat_id, "Sorry, something went wrong. Try again?")
        print(f"[telegram] text bg error: {e}")


def _handle_status_bg(chat_id: int, user_id: str):
    """Process /status in background thread."""
    try:
        drift = detect_drift(user_id)
        if drift["skipped"]:
            _send_message_sync(chat_id, f"📊 {drift['message']}")
        elif drift["detected"]:
            _send_message_sync(
                chat_id,
                f"📊 *Drift detected* ({drift['severity']})\n"
                f"Score: {drift['drift_score']:.3f}\n"
                f"Direction: {drift['sentiment_direction']}\n\n"
                f"{drift['message']}"
            )
            voice = _generate_voice_insight(drift)
            if voice:
                _send_voice_sync(chat_id, voice)
        else:
            _send_message_sync(chat_id, f"📊 *Stable*\n{drift['message']}")
    except Exception as e:
        _send_message_sync(chat_id, "Sorry, couldn't fetch status right now.")
        print(f"[telegram] status bg error: {e}")


def _handle_recap_bg(chat_id: int, user_id: str):
    """Process /recap in background thread."""
    try:
        recap_text = _generate_weekly_recap(user_id)
        _send_message_sync(chat_id, f"📅 *Weekly Recap*\n\n{recap_text}")

        from services.tts import text_to_speech
        voice = text_to_speech(recap_text)
        _send_voice_sync(chat_id, voice)
    except Exception as e:
        _send_message_sync(chat_id, "Sorry, couldn't generate recap right now.")
        print(f"[telegram] recap bg error: {e}")


# === Webhook — returns 200 INSTANTLY, processes in background ===

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates. Returns immediately, processes in background."""
    body = await request.json()

    # Dedup — prevent double processing from Telegram retries
    update_id = body.get("update_id")
    if update_id:
        if update_id in _processed_updates:
            return {"ok": True}
        _processed_updates.add(update_id)
        if len(_processed_updates) > _MAX_PROCESSED:
            _processed_updates.clear()

    message = body.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = f"tg_{chat_id}"

    if chat_id not in _user_registry:
        _user_registry[chat_id] = {"user_id": user_id}

    text = message.get("text", "").strip()

    # /start — respond inline (fast, no processing needed)
    if text.startswith("/start"):
        _send_message_sync(
            chat_id,
            "🌊 *Welcome to MoodDrift!*\n\n"
            "🎤 *Send a voice note* — tell me how you're feeling\n"
            "✍️ *Send text* — type your thoughts\n"
            "📊 /status — current drift\n"
            "📅 /recap — weekly summary\n\n"
            "_How are you feeling today?_"
        )
        return {"ok": True}

    # Everything else → background thread
    if text.startswith("/status"):
        threading.Thread(target=_handle_status_bg, args=(chat_id, user_id), daemon=True).start()
    elif text.startswith("/recap"):
        threading.Thread(target=_handle_recap_bg, args=(chat_id, user_id), daemon=True).start()
    elif message.get("voice"):
        file_id = message["voice"]["file_id"]
        threading.Thread(target=_handle_voice_bg, args=(chat_id, user_id, file_id), daemon=True).start()
    elif text and not text.startswith("/"):
        threading.Thread(target=_handle_text_bg, args=(chat_id, user_id, text), daemon=True).start()

    return {"ok": True}


# === Cron endpoints ===

@router.post("/telegram/nudge")
async def send_daily_nudge():
    """Feature 1: Send daily check-in nudge to all registered users."""
    import random
    nudge_messages = [
        "Hey, how are you feeling today? Send me a voice note or text 🎤",
        "Time for your daily check-in. How was your day? 🌙",
        "Quick check-in — what's on your mind today? 💭",
        "How are you doing? Even a one-line reply helps 📊",
    ]
    msg = random.choice(nudge_messages)

    sent = 0
    for chat_id in _user_registry:
        try:
            _send_message_sync(chat_id, msg)
            sent += 1
        except Exception as e:
            print(f"[telegram] nudge error for {chat_id}: {e}")

    return {"sent": sent, "total_users": len(_user_registry)}


@router.post("/telegram/weekly-recap")
async def send_weekly_recap():
    """Feature 5: Send weekly voice recap to all registered users."""
    sent = 0
    for chat_id, info in _user_registry.items():
        try:
            _handle_recap_bg(chat_id, info["user_id"])
            sent += 1
        except Exception as e:
            print(f"[telegram] weekly recap error for {chat_id}: {e}")

    return {"sent": sent, "total_users": len(_user_registry)}
