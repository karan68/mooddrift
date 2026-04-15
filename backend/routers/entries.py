from datetime import datetime, timezone

from fastapi import APIRouter

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
