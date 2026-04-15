"""
Telegram bot webhook handler.

Implements all 5 features from FEATURES.md:
1. Daily nudge at preferred time (via /telegram/nudge cron endpoint)
2. Receive voice notes → transcribe → embed → store → drift check → reply
3. Receive text → embed → store → drift check → reply
4. Send voice summary (TTS) when drift is detected
5. Weekly voice recap (via /telegram/weekly-recap cron endpoint)
"""

import json
from datetime import datetime, timezone, timedelta
from collections import Counter

import httpx
from fastapi import APIRouter, Request, Query

from config import settings
from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import upsert_entry, scroll_entries
from services.drift_engine import detect_drift
from services.transcription import transcribe_audio

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

# In-memory user registry (in production, use a DB)
# Maps telegram chat_id → preferences
_user_registry: dict[int, dict] = {}


async def _send_message(chat_id: int, text: str):
    """Send a text message to a Telegram chat."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )


async def _send_voice(chat_id: int, voice_bytes: bytes):
    """Send a voice note (MP3) to a Telegram chat."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendVoice",
            files={"voice": ("insight.mp3", voice_bytes, "audio/mpeg")},
            data={"chat_id": str(chat_id)},
            timeout=30,
        )


async def _download_file(file_id: str) -> bytes:
    """Download a file from Telegram by file_id."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TELEGRAM_API}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        resp = await client.get(
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
        # Clean markdown from message for TTS
        text = drift["message"].replace("*", "").replace("_", "")
        return text_to_speech(text)
    except Exception as e:
        print(f"[telegram] TTS error: {e}")
        return None


def _process_entry(user_id: str, transcript: str) -> dict:
    """Process a journal entry: embed, analyze, store, drift check."""
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
        "entry_type": "checkin",
    }

    point_id = upsert_entry(vector, payload)
    drift_result = detect_drift(user_id)

    return {
        "entry_id": point_id,
        "sentiment": sentiment,
        "keywords": keywords,
        "drift": drift_result,
    }


def _format_response(result: dict) -> str:
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

    # Top keywords across all entries this week
    all_keywords: list[str] = []
    for e in entries:
        all_keywords.extend(e.payload.get("keywords", []))
    keyword_counts = Counter(all_keywords)
    top_keywords = [kw for kw, _ in keyword_counts.most_common(3)]

    # Drift status
    drift = detect_drift(user_id)

    # Build recap
    parts = [f"Here's your weekly reflection."]
    parts.append(f"You checked in {entry_count} times this week.")

    if avg_sentiment > 0.2:
        parts.append("Your overall mood was positive.")
    elif avg_sentiment > -0.2:
        parts.append("Your overall mood was mixed — some good days, some tough ones.")
    else:
        parts.append("Your overall mood was lower than usual this week.")

    if top_keywords:
        parts.append(f"You mentioned {', '.join(top_keywords)} most often.")

    if drift["detected"]:
        parts.append(f"Your entries are showing {drift['severity']} drift. {drift['message']}")
    else:
        parts.append("Your patterns look consistent with your baseline. Keep up the practice.")

    parts.append("Take care of yourself.")

    return " ".join(parts)


# === Webhook handler ===

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates."""
    body = await request.json()
    message = body.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = f"tg_{chat_id}"

    # Register user
    if chat_id not in _user_registry:
        _user_registry[chat_id] = {"user_id": user_id, "registered": True}

    # /start command
    if message.get("text", "").startswith("/start"):
        await _send_message(
            chat_id,
            "🌊 *Welcome to MoodDrift!*\n\n"
            "I'm your voice journal companion. Here's how to use me:\n\n"
            "🎤 *Send a voice note* — tell me how you're feeling\n"
            "✍️ *Send a text* — type out your thoughts\n"
            "📊 /status — see your current emotional drift\n"
            "📅 /recap — get your weekly summary\n\n"
            "I'll check in with you daily and notice patterns "
            "you might miss. Everything you share stays private.\n\n"
            "_Send your first entry now — how are you feeling today?_"
        )
        return {"ok": True}

    # /status command
    if message.get("text", "").startswith("/status"):
        drift = detect_drift(user_id)
        if drift["skipped"]:
            await _send_message(chat_id, f"📊 {drift['message']}")
        elif drift["detected"]:
            await _send_message(
                chat_id,
                f"📊 *Drift detected* ({drift['severity']})\n"
                f"Score: {drift['drift_score']:.3f}\n"
                f"Direction: {drift['sentiment_direction']}\n\n"
                f"{drift['message']}"
            )
            # Feature 4: Send voice summary when drift detected
            voice = _generate_voice_insight(drift)
            if voice:
                await _send_voice(chat_id, voice)
        else:
            await _send_message(chat_id, f"📊 *Stable*\n{drift['message']}")
        return {"ok": True}

    # /recap command — on-demand weekly recap
    if message.get("text", "").startswith("/recap"):
        recap_text = _generate_weekly_recap(user_id)
        await _send_message(chat_id, f"📅 *Weekly Recap*\n\n{recap_text}")

        # Feature 5: Send as voice note too
        try:
            from services.tts import text_to_speech
            voice = text_to_speech(recap_text)
            await _send_voice(chat_id, voice)
        except Exception as e:
            print(f"[telegram] recap TTS error: {e}")

        return {"ok": True}

    # Voice note — Feature 2
    if message.get("voice"):
        file_id = message["voice"]["file_id"]
        await _send_message(chat_id, "🎧 _Listening to your voice note..._")

        try:
            audio_bytes = await _download_file(file_id)
            transcript = transcribe_audio(audio_bytes)

            if not transcript.strip():
                await _send_message(chat_id, "I couldn't make out what you said. Try again?")
                return {"ok": True}

            result = _process_entry(user_id, transcript)
            reply = _format_response(result)
            await _send_message(chat_id, reply)

            # Feature 4: If drift detected, also send voice insight
            if result["drift"]["detected"]:
                voice = _generate_voice_insight(result["drift"])
                if voice:
                    await _send_voice(chat_id, voice)

        except Exception as e:
            await _send_message(chat_id, "Sorry, something went wrong processing your voice note. Try sending text instead.")
            print(f"[telegram] voice note error: {e}")

        return {"ok": True}

    # Text message — Feature 3
    text = message.get("text", "").strip()
    if text and not text.startswith("/"):
        try:
            result = _process_entry(user_id, text)
            reply = _format_response(result)
            await _send_message(chat_id, reply)

            # Feature 4: If drift detected, also send voice insight
            if result["drift"]["detected"]:
                voice = _generate_voice_insight(result["drift"])
                if voice:
                    await _send_voice(chat_id, voice)

        except Exception as e:
            await _send_message(chat_id, "Sorry, something went wrong. Please try again.")
            print(f"[telegram] text error: {e}")

        return {"ok": True}

    return {"ok": True}


# === Cron endpoints (called by external scheduler like cron-job.org) ===

@router.post("/telegram/nudge")
async def send_daily_nudge():
    """Feature 1: Send daily check-in nudge to all registered users.

    Call this endpoint via an external cron service (e.g. cron-job.org)
    at the desired time (e.g. 8 PM IST daily).
    """
    nudge_messages = [
        "Hey, how are you feeling today? Send me a voice note or text 🎤",
        "Time for your daily check-in. How was your day? 🌙",
        "Quick check-in — what's on your mind today? I'm listening 💭",
        "How are you doing? Even a one-line reply helps track your patterns 📊",
    ]
    import random
    msg = random.choice(nudge_messages)

    sent = 0
    for chat_id in _user_registry:
        try:
            await _send_message(chat_id, msg)
            sent += 1
        except Exception as e:
            print(f"[telegram] nudge error for {chat_id}: {e}")

    return {"sent": sent, "total_users": len(_user_registry)}


@router.post("/telegram/weekly-recap")
async def send_weekly_recap():
    """Feature 5: Send weekly voice recap to all registered users.

    Call this endpoint via external cron (e.g. Sunday 8 PM IST).
    """
    sent = 0
    for chat_id, info in _user_registry.items():
        user_id = info["user_id"]
        try:
            recap_text = _generate_weekly_recap(user_id)
            await _send_message(chat_id, f"📅 *Your Weekly Recap*\n\n{recap_text}")

            # Send as voice note
            from services.tts import text_to_speech
            voice = text_to_speech(recap_text)
            await _send_voice(chat_id, voice)
            sent += 1
        except Exception as e:
            print(f"[telegram] weekly recap error for {chat_id}: {e}")

    return {"sent": sent, "total_users": len(_user_registry)}
