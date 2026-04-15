"""Transcribe audio files using Groq Whisper API."""

import httpx
from config import settings

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe audio bytes using Groq Whisper. Returns transcript text."""
    resp = httpx.post(
        GROQ_WHISPER_URL,
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        files={"file": (filename, audio_bytes, "audio/ogg")},
        data={"model": "whisper-large-v3", "language": "en"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("text", "")
