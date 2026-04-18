from pydantic import BaseModel
from typing import List, Optional


class MoodEntryPayload(BaseModel):
    user_id: str
    date: str                    # "2026-04-14"
    timestamp: int               # Unix timestamp
    transcript: str
    sentiment_score: float       # -1.0 (very negative) to 1.0 (very positive)
    keywords: List[str]
    week_number: int
    month: str                   # "2026-04"
    entry_type: str = "checkin"  # "checkin" | "reflection" | "followup" | "coping_strategy"

    # === Voice biomarkers (optional — only set for voice-note entries) ===
    pitch_mean: Optional[float] = None          # Hz
    pitch_std: Optional[float] = None           # Hz
    speech_rate: Optional[float] = None         # syllables / sec
    pause_ratio: Optional[float] = None         # 0..1
    energy_mean: Optional[float] = None         # RMS
    jitter: Optional[float] = None              # relative
    vocal_stress_score: Optional[float] = None  # 0..1 composite
    audio_duration: Optional[float] = None      # seconds
    text_voice_congruence: Optional[float] = None  # 0..1 (1 = aligned)
    voice_incongruent: Optional[bool] = None    # True when text/voice mismatch


class MoodEntryCreate(BaseModel):
    user_id: str
    transcript: str
    entry_type: str = "checkin"


class MoodEntryResponse(BaseModel):
    id: str
    payload: MoodEntryPayload
    score: Optional[float] = None
