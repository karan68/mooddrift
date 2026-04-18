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


def _process_entry(
    user_id: str,
    transcript: str,
    entry_type: str = "checkin",
    biomarkers: dict | None = None,
) -> dict:
    """Process a journal entry: embed, analyze, store, drift check.

    If `biomarkers` is provided (voice-note entries only), it's merged into the
    Qdrant payload and incongruence detection is run against the user's
    personal vocal baseline.
    """
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

    # === Voice biomarkers (optional) ===
    congruence = None
    if biomarkers:
        # Compute personal baseline BEFORE storing this new entry, so the new
        # one isn't included in its own baseline.
        from services.voice_biomarkers import (
            compute_user_baseline,
            analyze_congruence,
        )
        baseline = compute_user_baseline(user_id)
        congruence = analyze_congruence(biomarkers, sentiment, baseline)

        # Merge biomarker fields into payload (None values skipped).
        for key in (
            "pitch_mean", "pitch_std", "speech_rate", "pause_ratio",
            "energy_mean", "jitter", "vocal_stress_score", "audio_duration",
        ):
            if biomarkers.get(key) is not None:
                payload[key] = biomarkers[key]
        payload["text_voice_congruence"] = congruence["congruence_score"]
        payload["voice_incongruent"] = congruence["incongruent"]

    point_id = upsert_entry(vector, payload)
    drift_result = detect_drift(user_id)

    return {
        "entry_id": point_id,
        "sentiment": sentiment,
        "keywords": keywords,
        "drift": drift_result,
        "biomarkers": biomarkers,
        "congruence": congruence,
    }


# Track users who were asked "what helped?" — awaiting coping response
_awaiting_coping: set[int] = set()

# Track users who were prompted to record a time capsule
_awaiting_capsule: set[int] = set()


def _format_response(result: dict, chat_id: int | None = None, user_id: str | None = None) -> str:
    """Format the processing result into a user-friendly text reply."""
    sentiment = result["sentiment"]
    keywords = result["keywords"]
    drift = result["drift"]
    congruence = result.get("congruence")

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

    # === Agent memory: context-aware follow-up ===
    if user_id:
        try:
            from services.agent_memory import build_agent_context, format_context_for_telegram
            context = build_agent_context(user_id)
            memory_line = format_context_for_telegram(context, sentiment)
            if memory_line:
                lines.append(f"\n{memory_line}")
        except Exception as e:
            print(f"[telegram] agent memory error: {e}")

    if drift["skipped"]:
        lines.append(f"\n_{drift['message']}_")
    elif drift["detected"]:
        lines.append(f"\n⚠️ *Drift detected* ({drift['severity']})")
        lines.append(drift["message"])
    else:
        lines.append(f"\n✦ {drift['message']}")

    # === Voice-text incongruence (X-factor signal) ===
    # When the text and voice tell different stories, surface it gently.
    if congruence and congruence.get("incongruent") and congruence.get("message"):
        lines.append(f"\n🎙️ *Voice check-in*")
        lines.append(congruence["message"])

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
    """Generate a weekly recap using Groq LLM for natural, warm language."""
    now = datetime.now(timezone.utc)
    week_ago = int((now - timedelta(days=7)).timestamp())
    entries = scroll_entries(user_id=user_id, date_from=week_ago, limit=50)

    if not entries:
        return "You didn't check in this week. No worries — I'll be here when you're ready."

    # Gather data for the LLM prompt
    entry_count = len(entries)
    sentiments = [e.payload.get("sentiment_score", 0) for e in entries]
    avg_sentiment = sum(sentiments) / len(sentiments)

    all_keywords: list[str] = []
    for e in entries:
        all_keywords.extend(e.payload.get("keywords", []))
    keyword_counts = Counter(all_keywords)
    top_keywords = [kw for kw, count in keyword_counts.most_common(5) if count >= 2]

    # Get sample transcripts (most negative + most positive)
    sorted_entries = sorted(entries, key=lambda e: e.payload.get("sentiment_score", 0))
    sample_negative = sorted_entries[0].payload.get("transcript", "")[:100] if sentiments else ""
    sample_positive = sorted_entries[-1].payload.get("transcript", "")[:100] if sentiments else ""

    drift = detect_drift(user_id)
    coping = drift.get("coping_strategies")

    # Build structured prompt for Groq LLM
    prompt = f"""Generate a warm, personal weekly reflection for a journal app user.

Data from their week:
- Check-ins: {entry_count}
- Average mood: {"positive" if avg_sentiment > 0.2 else "mixed" if avg_sentiment > -0.2 else "lower than usual"} ({avg_sentiment:.2f})
- Recurring themes: {', '.join(top_keywords) if top_keywords else 'varied topics'}
- Most difficult moment: "{sample_negative}"
- Best moment: "{sample_positive}"
- Drift status: {"detected — " + drift['severity'] + " level" if drift.get('detected') else "stable, no drift"}
- Matching past period: {drift.get('matching_period') or 'none'}
- What helped last time: {coping[0][:100] if coping else 'no coping strategies recorded yet'}

Write a 3-4 sentence voice note script. Start with "Here's your weekly reflection." Be warm and specific. End with encouragement. Do NOT use clinical language or emojis."""

    try:
        from services.llm_summary import generate_summary
        return generate_summary(prompt)
    except Exception as e:
        print(f"[telegram] LLM recap error, falling back to template: {e}")
        # Fallback to simple template if LLM fails
        parts = [f"Here's your weekly reflection. You checked in {entry_count} times."]
        if avg_sentiment > 0.2:
            parts.append("Overall your mood was positive this week.")
        elif avg_sentiment < -0.2:
            parts.append("It seems like a tougher week than usual.")
        else:
            parts.append("Your mood was mixed this week.")
        if drift.get("detected"):
            parts.append(drift["message"])
        parts.append("Take care of yourself.")
        return " ".join(parts)


# === Background processing functions ===

def _check_capsule_and_drift(chat_id: int, user_id: str, result: dict, audio_bytes: bytes | None = None):
    """After processing an entry, handle capsule prompting + drift playback."""
    drift = result["drift"]

    # === On drift: play back a time capsule if one exists ===
    if drift["detected"]:
        voice = _generate_voice_insight(drift)
        if voice:
            _send_voice_sync(chat_id, voice)
        try:
            from services.time_capsule import get_capsule_for_playback, get_capsule_audio_path
            capsule = get_capsule_for_playback(user_id)
            if capsule:
                _send_message_sync(
                    chat_id,
                    f"💊 *A message from you on {capsule['date']}*\n"
                    f"You recorded this when you were feeling good:\n\n"
                    f"_\"{capsule['transcript'][:300]}\"_"
                )
                if capsule.get("audio_filename"):
                    path = get_capsule_audio_path(capsule["audio_filename"])
                    if path:
                        _send_voice_sync(chat_id, path.read_bytes())
        except Exception as e:
            print(f"[telegram] capsule playback error: {e}")
        return

    # === On positive streak: prompt capsule recording ===
    if result["sentiment"] > 0.3 and not drift.get("skipped"):
        try:
            from services.time_capsule import check_capsule_ready
            readiness = check_capsule_ready(user_id)
            if readiness["ready"]:
                _send_message_sync(
                    chat_id,
                    f"🌟 *{readiness['streak']} good days in a row!*\n\n"
                    "Want to record a message to your future self? "
                    "Something you'd want to hear on a tough day.\n\n"
                    "_Send a voice note or text and I'll save it as a "
                    "time capsule for you._ 💛"
                )
                _awaiting_capsule.add(chat_id)
        except Exception as e:
            print(f"[telegram] capsule readiness check error: {e}")


def _handle_voice_bg(chat_id: int, user_id: str, file_id: str):
    """Process voice note in background thread."""
    try:
        _send_message_sync(chat_id, "🎧 _Listening..._")
        from services.transcription import transcribe_audio
        from services.voice_biomarkers import extract_biomarkers

        audio_bytes = _download_file_sync(file_id)
        transcript = transcribe_audio(audio_bytes)

        if not transcript.strip():
            _send_message_sync(chat_id, "I couldn't make out what you said. Try again?")
            return

        # Check if user was prompted to record a time capsule
        if chat_id in _awaiting_capsule:
            _awaiting_capsule.discard(chat_id)
            try:
                from services.time_capsule import save_capsule_audio, store_capsule
                from services.embedding import generate_embedding
                from services.sentiment import analyze_sentiment

                audio_filename = save_capsule_audio(audio_bytes, extension="ogg")
                sentiment = analyze_sentiment(transcript)
                vector = generate_embedding(transcript)
                store_capsule(user_id, transcript, audio_filename, sentiment, vector)
                _send_message_sync(
                    chat_id,
                    "💛 *Time capsule saved.*\n\n"
                    "I'll play this back if you ever need to hear it. "
                    "Your future self will thank you."
                )
                return
            except Exception as e:
                print(f"[telegram] capsule save error: {e}")
                # Fall through to normal processing

        # Extract acoustic biomarkers from the same audio bytes.
        # Returns None if librosa/ffmpeg can't decode — pipeline still proceeds.
        try:
            biomarkers = extract_biomarkers(audio_bytes, transcript=transcript)
        except Exception as bm_err:
            print(f"[telegram] biomarker extraction error: {bm_err}")
            biomarkers = None

        result = _process_entry(user_id, transcript, biomarkers=biomarkers)
        _send_message_sync(chat_id, _format_response(result, chat_id, user_id))

        _check_capsule_and_drift(chat_id, user_id, result, audio_bytes)
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

        # Check if user was prompted to record a time capsule (text version)
        if chat_id in _awaiting_capsule:
            _awaiting_capsule.discard(chat_id)
            try:
                from services.time_capsule import store_capsule
                from services.embedding import generate_embedding
                from services.sentiment import analyze_sentiment

                sentiment = analyze_sentiment(text)
                vector = generate_embedding(text)
                store_capsule(user_id, text, None, sentiment, vector)
                _send_message_sync(
                    chat_id,
                    "💛 *Time capsule saved.*\n\n"
                    "I'll play this back if you ever need to hear it."
                )
                return
            except Exception as e:
                print(f"[telegram] text capsule save error: {e}")

        result = _process_entry(user_id, text)
        _send_message_sync(chat_id, _format_response(result, chat_id, user_id))

        _check_capsule_and_drift(chat_id, user_id, result)
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
        _user_registry[chat_id]["first_name"] = message.get("from", {}).get("first_name", "")
        _send_message_sync(
            chat_id,
            "🌊 *Welcome to MoodDrift!*\n\n"
            "🎤 *Send a voice note* — tell me how you're feeling\n"
            "✍️ *Send text* — type your thoughts\n"
            "📊 /status — current drift\n"
            "📅 /recap — weekly summary\n"
            "🤝 /trust @username — set trusted contact\n"
            "❌ /untrust — remove trusted contact\n\n"
            "_How are you feeling today?_"
        )
        return {"ok": True}

    # /trust — set trusted contact
    if text.startswith("/trust"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            _send_message_sync(chat_id, "Usage: /trust @username or /trust 9876543210")
        else:
            contact = parts[1].strip()
            _set_trusted_contact(chat_id, contact)
            _send_message_sync(
                chat_id,
                f"✅ Trusted contact set to *{contact}*.\n\n"
                f"If your emotional drift stays high for several days, "
                f"we'll send them a gentle heads-up. "
                f"We will *never* share your journal entries — only that you might need support.\n\n"
                f"Use /untrust to remove anytime."
            )
        return {"ok": True}

    # /untrust — remove trusted contact
    if text.startswith("/untrust"):
        _remove_trusted_contact(chat_id)
        _send_message_sync(chat_id, "✅ Trusted contact removed. No one will be notified.")
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


# === P2: Trusted Contact Alerts ===

def _set_trusted_contact(chat_id: int, contact: str):
    """Set a trusted contact for a user."""
    if chat_id in _user_registry:
        _user_registry[chat_id]["trusted_contact"] = contact
        _user_registry[chat_id]["trusted_enabled"] = True


def _remove_trusted_contact(chat_id: int):
    """Remove trusted contact for a user."""
    if chat_id in _user_registry:
        _user_registry[chat_id].pop("trusted_contact", None)
        _user_registry[chat_id]["trusted_enabled"] = False


@router.post("/telegram/check-trusted-alerts")
async def check_trusted_alerts():
    """P2: Check all users for sustained high drift and alert trusted contacts.

    Call via cron (e.g. daily). Only alerts if:
    - User has opted in with a trusted contact
    - Drift score >= 0.5
    """
    alerted = 0
    for chat_id, info in _user_registry.items():
        if not info.get("trusted_enabled") or not info.get("trusted_contact"):
            continue

        user_id = info["user_id"]
        drift = detect_drift(user_id)

        if drift.get("detected") and drift.get("drift_score", 0) >= 0.5:
            contact = info["trusted_contact"]
            user_name = info.get("first_name", "Someone you care about")

            alert_msg = (
                f"Hi — {user_name} has given you permission to receive this message. "
                f"Their recent journal entries suggest they may be going through a "
                f"difficult time. You might want to check in with them. "
                f"No entry content is shared — only that a pattern was noticed. "
                f"— MoodDrift"
            )

            try:
                contact_id = int(contact)
                _send_message_sync(contact_id, alert_msg)
            except ValueError:
                _send_message_sync(
                    chat_id,
                    f"⚠️ Your drift has been elevated. "
                    f"We'd like to notify your trusted contact ({contact}), "
                    f"but we can only auto-send to Telegram users. "
                    f"Please reach out to them yourself, or share this:\n\n_{alert_msg}_"
                )

            alerted += 1

    return {"alerted": alerted}


# === P2: Consistency Acknowledgment ===

@router.post("/telegram/check-consistency")
async def check_consistency():
    """P2: Acknowledge journaling consistency milestones.

    Call via daily cron. Checks 7, 14, 30 day milestones.
    No gamification — encouragement only.
    """
    milestones = [
        (30, "You've been journaling for a month. That takes real commitment. Patterns become much clearer with this much data. Keep going."),
        (14, "Two weeks of checking in. You're building a real picture of your emotional patterns. That self-awareness is powerful."),
        (7, "One week of journaling. You've taken the first step toward understanding your patterns. That matters."),
    ]

    acknowledged = 0
    for chat_id, info in _user_registry.items():
        user_id = info["user_id"]
        already_acked = info.get("last_consistency_milestone", 0)

        now = datetime.now(timezone.utc)
        for days, message in milestones:
            if days <= already_acked:
                continue
            date_from = int((now - timedelta(days=days)).timestamp())
            entries = scroll_entries(user_id=user_id, date_from=date_from, limit=200)
            if len(entries) >= days:
                _send_message_sync(chat_id, f"🌟 {message}")
                info["last_consistency_milestone"] = days
                acknowledged += 1
                break

    return {"acknowledged": acknowledged}
