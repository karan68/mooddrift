from datetime import datetime, timezone

from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings
from models.schemas import MoodEntryCreate
from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import upsert_entry

router = APIRouter()


@router.post("/api/entries")
def create_entry(entry: MoodEntryCreate):
    """Manually create a mood entry (for testing without Vapi)."""
    vector = generate_embedding(entry.transcript)
    sentiment = analyze_sentiment(entry.transcript)
    keywords = extract_keywords(entry.transcript)

    now = datetime.now(timezone.utc)
    payload = {
        "user_id": entry.user_id,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": int(now.timestamp()),
        "transcript": entry.transcript,
        "sentiment_score": sentiment,
        "keywords": keywords,
        "week_number": now.isocalendar()[1],
        "month": now.strftime("%Y-%m"),
        "entry_type": entry.entry_type,
    }

    point_id = upsert_entry(vector, payload)

    return {
        "id": point_id,
        "sentiment_score": sentiment,
        "keywords": keywords,
    }


@router.post("/api/voice-entry")
async def create_voice_entry(
    audio: UploadFile = File(...),
    user_id: str = Form(default="demo_user"),
    entry_type: str = Form(default="checkin"),
):
    """Create a mood entry from a voice recording (dashboard upload).

    Accepts an audio file, transcribes it via Groq Whisper, extracts voice
    biomarkers via librosa, then runs the full pipeline (embed, sentiment,
    keywords, drift check, congruence detection).

    This is the dashboard counterpart of the Telegram voice-note handler.
    """
    from services.transcription import transcribe_audio
    from services.voice_biomarkers import (
        extract_biomarkers,
        compute_user_baseline,
        analyze_congruence,
    )
    from services.drift_engine import detect_drift

    audio_bytes = await audio.read()
    if not audio_bytes:
        return {"error": "Empty audio file"}

    # Transcribe
    transcript = transcribe_audio(audio_bytes)
    if not transcript or not transcript.strip():
        return {"error": "Could not transcribe audio. Try speaking more clearly."}

    # Extract voice biomarkers
    try:
        biomarkers = extract_biomarkers(audio_bytes, transcript=transcript)
    except Exception:
        biomarkers = None

    # Standard pipeline
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

    # Merge biomarkers + congruence if available
    congruence = None
    if biomarkers:
        baseline = compute_user_baseline(user_id)
        congruence = analyze_congruence(biomarkers, sentiment, baseline)

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
        "id": point_id,
        "transcript": transcript,
        "sentiment_score": sentiment,
        "keywords": keywords,
        "biomarkers": biomarkers,
        "congruence": congruence,
        "drift": drift_result,
    }


class EntryUpdate(BaseModel):
    transcript: Optional[str] = None


@router.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: str):
    """Delete a single journal entry by its Qdrant point ID."""
    from services.qdrant_service import delete_single_entry
    success = delete_single_entry(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True, "id": entry_id}


@router.patch("/api/entries/{entry_id}")
def update_entry(entry_id: str, body: EntryUpdate):
    """Edit a journal entry's transcript. Re-runs sentiment + keyword analysis."""
    from services.qdrant_service import update_entry_payload

    if not body.transcript or not body.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")

    new_sentiment = analyze_sentiment(body.transcript)
    new_keywords = extract_keywords(body.transcript)

    updates = {
        "transcript": body.transcript.strip(),
        "sentiment_score": new_sentiment,
        "keywords": new_keywords,
    }
    success = update_entry_payload(entry_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {
        "id": entry_id,
        "transcript": body.transcript.strip(),
        "sentiment_score": new_sentiment,
        "keywords": new_keywords,
    }
