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
    entry_type: str = "checkin"  # "checkin" | "reflection" | "followup"


class MoodEntryCreate(BaseModel):
    user_id: str
    transcript: str
    entry_type: str = "checkin"


class MoodEntryResponse(BaseModel):
    id: str
    payload: MoodEntryPayload
    score: Optional[float] = None
