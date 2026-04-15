"""
Dashboard API endpoints (Phase 4).

Per PROJECT.md Section 12:
  GET /api/entries?user_id=&days=90  — entries within a time window
  GET /api/drift-timeline?user_id=   — weekly drift scores for chart
  GET /api/drift-current?user_id=    — current drift status
  GET /api/visualization?user_id=    — UMAP-reduced 2D coordinates for scatter plot
"""

from datetime import datetime, timezone, timedelta
from collections import defaultdict

import numpy as np
from fastapi import APIRouter, Query

from config import settings
from services.qdrant_service import scroll_entries, delete_entries
from services.drift_engine import (
    compute_centroid,
    cosine_similarity,
    detect_drift,
)

router = APIRouter()


@router.get("/api/entries")
def get_entries(
    user_id: str = Query(default=None),
    days: int = Query(default=90),
):
    """Get all entries for a user within a time window."""
    uid = user_id or settings.default_user_id
    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())

    entries = scroll_entries(user_id=uid, date_from=date_from, limit=200)

    result = []
    for e in entries:
        result.append({
            "id": e.id,
            "date": e.payload.get("date"),
            "timestamp": e.payload.get("timestamp"),
            "transcript": e.payload.get("transcript"),
            "sentiment_score": e.payload.get("sentiment_score"),
            "keywords": e.payload.get("keywords", []),
            "entry_type": e.payload.get("entry_type"),
        })

    # Sort by date
    result.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return {"entries": result, "total": len(result)}


@router.get("/api/drift-timeline")
def get_drift_timeline(
    user_id: str = Query(default=None),
    days: int = Query(default=90),
):
    """Weekly drift scores for the drift timeline chart.

    Computes a rolling drift score per week by comparing each week's centroid
    against the centroid of all entries before that week.
    """
    uid = user_id or settings.default_user_id
    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())

    entries = scroll_entries(user_id=uid, date_from=date_from, limit=200)

    if len(entries) < 5:
        return {"timeline": [], "message": "Not enough entries for timeline"}

    # Group entries by ISO week
    weeks: dict[str, list] = defaultdict(list)
    for e in entries:
        date_str = e.payload.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            iso = dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
        except ValueError:
            continue
        weeks[week_key].append(e)

    sorted_weeks = sorted(weeks.keys())

    if len(sorted_weeks) < 2:
        return {"timeline": [], "message": "Need at least 2 weeks of data"}

    timeline = []
    # For each week, compute drift score against all prior weeks
    all_prior_vectors = []
    for week_key in sorted_weeks:
        week_entries = weeks[week_key]
        week_vectors = [e.vector for e in week_entries]
        week_centroid = compute_centroid(week_vectors)

        # Average sentiment for this week
        sentiments = [e.payload.get("sentiment_score", 0) for e in week_entries]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0

        if all_prior_vectors:
            prior_centroid = compute_centroid(all_prior_vectors)
            sim = cosine_similarity(week_centroid, prior_centroid)
            drift_score = round(1.0 - sim, 4)
        else:
            drift_score = 0.0

        # Get the Monday date for this week
        week_dates = [e.payload.get("date", "") for e in week_entries]
        week_start = min(week_dates) if week_dates else week_key

        timeline.append({
            "week": week_key,
            "week_start": week_start,
            "drift_score": drift_score,
            "avg_sentiment": round(avg_sentiment, 3),
            "entry_count": len(week_entries),
        })

        all_prior_vectors.extend(week_vectors)

    return {"timeline": timeline}


@router.get("/api/drift-current")
def get_drift_current(user_id: str = Query(default=None)):
    """Current drift status — calls detect_drift from drift_engine."""
    uid = user_id or settings.default_user_id
    return detect_drift(uid)


@router.get("/api/visualization")
def get_visualization(
    user_id: str = Query(default=None),
    days: int = Query(default=90),
):
    """UMAP-reduced 2D coordinates for scatter plot visualization."""
    uid = user_id or settings.default_user_id
    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())

    entries = scroll_entries(user_id=uid, date_from=date_from, limit=200)

    if len(entries) < 5:
        return {"points": [], "message": "Not enough entries for visualization"}

    vectors = np.array([e.vector for e in entries])

    # Try UMAP, fall back to PCA if not available
    try:
        from umap import UMAP

        reducer = UMAP(
            n_components=2,
            n_neighbors=min(15, len(entries) - 1),
            min_dist=0.1,
            random_state=42,
        )
        coords = reducer.fit_transform(vectors)
    except ImportError:
        # Fallback: PCA
        from sklearn.decomposition import PCA

        reducer = PCA(n_components=2, random_state=42)
        coords = reducer.fit_transform(vectors)

    points = []
    for i, e in enumerate(entries):
        points.append({
            "id": e.id,
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
            "date": e.payload.get("date"),
            "sentiment_score": e.payload.get("sentiment_score"),
            "keywords": e.payload.get("keywords", []),
            "transcript": e.payload.get("transcript", "")[:100],
        })

    return {"points": points}


@router.post("/api/seed")
def seed_data():
    """Seed 60 demo entries. For dev/demo use only."""
    from seed.seed_data import seed
    seed()
    return {"status": "seeded", "entries": 60}


@router.delete("/api/entries")
def clear_entries(user_id: str = Query(default=None)):
    """Delete all entries for a user. For dev/demo use only."""
    uid = user_id or settings.default_user_id
    count = delete_entries(uid)
    return {"status": "cleared", "deleted": count}
