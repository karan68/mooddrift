"""
Telegram bot webhook handler.

Handles:
- Voice notes → transcribe → embed → store → drift check → reply
- Text messages → embed → store → drift check → reply
- /start command → welcome message
- /status command → current drift status
"""

import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request

from config import settings
from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import upsert_entry
from services.drift_engine import detect_drift
from services.transcription import transcribe_audio

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


async def _send_message(chat_id: int, text: str):
    """Send a text message to a Telegram chat."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )


async def _send_voice(chat_id: int, voice_bytes: bytes):
    """Send a voice note to a Telegram chat."""
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendVoice",
            files={"voice": ("summary.ogg", voice_bytes, "audio/ogg")},
            data={"chat_id": str(chat_id)},
            timeout=15,
        )


async def _download_file(file_id: str) -> bytes:
    """Download a file from Telegram by file_id."""
    async with httpx.AsyncClient() as client:
        # Get file path
        resp = await client.get(
            f"{TELEGRAM_API}/getFile",
            params={"file_id": file_id},
            timeout=10,
        )
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        # Download file
        resp = await client.get(
            f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}",
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content


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
    """Format the processing result into a user-friendly reply."""
    sentiment = result["sentiment"]
    keywords = result["keywords"]
    drift = result["drift"]

    # Sentiment emoji
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


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates."""
    body = await request.json()
    message = body.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = f"tg_{chat_id}"

    # /start command
    if message.get("text", "").startswith("/start"):
        await _send_message(
            chat_id,
            "🌊 *Welcome to MoodDrift!*\n\n"
            "I'm your voice journal companion. Here's how to use me:\n\n"
            "🎤 *Send a voice note* — tell me how you're feeling\n"
            "✍️ *Send a text* — type out your thoughts\n"
            "📊 /status — see your current emotional drift\n\n"
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
        else:
            await _send_message(
                chat_id,
                f"📊 *Stable*\n{drift['message']}"
            )
        return {"ok": True}

    # Voice note
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

        except Exception as e:
            await _send_message(chat_id, f"Sorry, something went wrong processing your voice note. Try sending text instead.")
            print(f"[telegram] voice note error: {e}")

        return {"ok": True}

    # Text message
    text = message.get("text", "").strip()
    if text and not text.startswith("/"):
        try:
            result = _process_entry(user_id, text)
            reply = _format_response(result)
            await _send_message(chat_id, reply)
        except Exception as e:
            await _send_message(chat_id, "Sorry, something went wrong. Please try again.")
            print(f"[telegram] text error: {e}")

        return {"ok": True}

    return {"ok": True}
