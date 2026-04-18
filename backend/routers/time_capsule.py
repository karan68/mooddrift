"""
Time Capsule API endpoints.

POST /api/time-capsule          — Upload a capsule recording (audio + transcript)
GET  /api/time-capsules         — List all capsules for a user
GET  /api/time-capsule/ready    — Check if user should be prompted to record
GET  /api/time-capsule/{id}/audio — Stream capsule audio for playback
"""

from fastapi import APIRouter, File, UploadFile, Form, Query, HTTPException
from fastapi.responses import FileResponse

from config import settings
from services.time_capsule import (
    save_capsule_audio,
    get_capsule_audio_path,
    store_capsule,
    check_capsule_ready,
    find_capsules_for_drift,
    get_capsule_for_playback,
    get_capsules_opening_today,
)

router = APIRouter()


@router.post("/api/time-capsule")
async def create_time_capsule(
    audio: UploadFile = File(None),
    transcript: str = Form(default=""),
    user_id: str = Form(default="demo_user"),
    open_date: str = Form(default=""),
):
    """Record a time capsule — voice + text stored in Qdrant with audio on disk.

    Accepts an optional audio file.  If audio is provided, it's transcribed
    (unless transcript is already given) and voice biomarkers are extracted.
    The capsule is stored as entry_type="time_capsule" in Qdrant.
    """
    from services.embedding import generate_embedding
    from services.sentiment import analyze_sentiment

    audio_bytes = None
    audio_filename = None

    if audio is not None:
        audio_bytes = await audio.read()
        if audio_bytes and len(audio_bytes) > 500:
            audio_filename = save_capsule_audio(audio_bytes)

            # If no transcript provided, transcribe the audio
            if not transcript.strip():
                try:
                    from services.transcription import transcribe_audio
                    transcript = transcribe_audio(audio_bytes)
                except Exception as e:
                    print(f"[time-capsule] transcription error: {e}")

    if not transcript.strip():
        return {"error": "No transcript provided and could not transcribe audio."}

    sentiment = analyze_sentiment(transcript)
    vector = generate_embedding(transcript)

    point_id = store_capsule(
        user_id=user_id,
        transcript=transcript,
        audio_filename=audio_filename,
        sentiment=sentiment,
        vector=vector,
        open_date=open_date.strip() if open_date.strip() else None,
    )

    return {
        "id": point_id,
        "transcript": transcript,
        "sentiment": sentiment,
        "has_audio": audio_filename is not None,
        "audio_filename": audio_filename,
    }


@router.get("/api/time-capsules")
def list_time_capsules(
    user_id: str = Query(default=None),
    days: int = Query(default=180),
):
    """List all time capsules for a user, most recent first."""
    uid = user_id or settings.default_user_id
    capsules = find_capsules_for_drift(uid, days=days)

    # Also check if the user is ready to record a new one
    readiness = check_capsule_ready(uid)

    return {
        "capsules": capsules,
        "total": len(capsules),
        "capsule_ready": readiness,
    }


@router.get("/api/time-capsule/ready")
def capsule_ready_check(
    user_id: str = Query(default=None),
):
    """Check if the user should be prompted to record a time capsule."""
    uid = user_id or settings.default_user_id
    return check_capsule_ready(uid)


@router.get("/api/time-capsule/playback")
def capsule_playback(
    user_id: str = Query(default=None),
):
    """Get the best capsule to play back during a drift.

    Returns the capsule metadata (including transcript).  Use
    /api/time-capsule/{id}/audio to stream the actual audio.
    """
    uid = user_id or settings.default_user_id
    capsule = get_capsule_for_playback(uid)
    if not capsule:
        return {"capsule": None, "message": "No time capsules recorded yet."}
    return {
        "capsule": capsule,
        "message": f"You recorded this on {capsule['date']} when you were feeling good.",
    }


@router.get("/api/time-capsule/{capsule_id}/audio")
def stream_capsule_audio(capsule_id: str):
    """Stream a capsule's audio file for browser playback.

    The capsule_id here is actually the audio_filename stored in Qdrant.
    """
    path = get_capsule_audio_path(capsule_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Capsule audio not found")

    # Determine media type from extension
    suffix = path.suffix.lower()
    media_types = {
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(path, media_type=media_type)


@router.get("/api/time-capsule/notifications")
def capsule_notifications(
    user_id: str = Query(default=None),
):
    """Check if any time capsules are due to open today.

    Returns capsules whose open_date is today or earlier.
    Used by the dashboard to show a notification banner.
    """
    uid = user_id or settings.default_user_id
    opening = get_capsules_opening_today(uid)
    return {
        "capsules": opening,
        "count": len(opening),
        "has_notifications": len(opening) > 0,
    }
