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
from services.qdrant_service import scroll_entries, delete_entries, search_coping_strategies
from services.drift_engine import (
    compute_centroid,
    cosine_similarity,
    detect_drift,
)

router = APIRouter()


@router.get("/api/context")
def get_user_context(
    user_id: str = Query(default=None),
):
    """Get the user's recent context for agent memory injection.

    Returns structured context: last entry, recent themes, sentiment trend,
    drift status, known triggers, capsule availability.
    """
    from services.agent_memory import build_agent_context
    uid = user_id or settings.default_user_id
    return build_agent_context(uid)


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
        # Hide time capsules from the regular journal view
        if e.payload.get("entry_type") == "time_capsule":
            continue
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


@router.get("/api/voice-biomarkers")
def get_voice_biomarkers(
    user_id: str = Query(default=None),
    days: int = Query(default=90),
):
    """Voice biomarker time series + personal baseline + incongruence flags.

    Powers the "Voice vs Text" panel in the dashboard. Returns:
      - timeline: per-entry list of date, text sentiment, vocal stress score,
        congruence score, and incongruence flag.
      - baseline: the user's personal vocal baseline (mean+std per feature).
      - latest_incongruence: the most recent incongruent entry, if any.
      - summary: counts and aggregates over the window.

    Only entries with stored biomarker fields are included.
    """
    from services.voice_biomarkers import compute_user_baseline

    uid = user_id or settings.default_user_id
    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())

    entries = scroll_entries(user_id=uid, date_from=date_from, limit=200)

    timeline = []
    for e in entries:
        payload = e.payload or {}
        if payload.get("vocal_stress_score") is None:
            continue
        timeline.append({
            "id": e.id,
            "date": payload.get("date"),
            "timestamp": payload.get("timestamp"),
            "text_sentiment": payload.get("sentiment_score"),
            "vocal_stress_score": payload.get("vocal_stress_score"),
            "pitch_mean": payload.get("pitch_mean"),
            "pitch_std": payload.get("pitch_std"),
            "speech_rate": payload.get("speech_rate"),
            "pause_ratio": payload.get("pause_ratio"),
            "energy_mean": payload.get("energy_mean"),
            "jitter": payload.get("jitter"),
            "audio_duration": payload.get("audio_duration"),
            "text_voice_congruence": payload.get("text_voice_congruence"),
            "voice_incongruent": payload.get("voice_incongruent", False),
            "transcript": (payload.get("transcript") or "")[:160],
        })

    timeline.sort(key=lambda p: p.get("timestamp") or 0)

    baseline = compute_user_baseline(uid, days=days)

    incongruent_points = [p for p in timeline if p.get("voice_incongruent")]
    latest_incongruence = incongruent_points[-1] if incongruent_points else None

    avg_stress = (
        round(sum(p["vocal_stress_score"] for p in timeline) / len(timeline), 4)
        if timeline else None
    )
    avg_congruence = (
        round(
            sum(p["text_voice_congruence"] or 0.0 for p in timeline) / len(timeline),
            4,
        )
        if timeline else None
    )

    return {
        "timeline": timeline,
        "baseline": baseline,
        "latest_incongruence": latest_incongruence,
        "summary": {
            "total_voice_entries": len(timeline),
            "incongruent_count": len(incongruent_points),
            "avg_vocal_stress": avg_stress,
            "avg_congruence": avg_congruence,
        },
    }


@router.delete("/api/entries")
def clear_entries(user_id: str = Query(default=None)):
    """Delete all entries for a user. For dev/demo use only."""
    uid = user_id or settings.default_user_id
    count = delete_entries(uid)
    return {"status": "cleared", "deleted": count}


@router.get("/api/triggers")
def get_triggers(
    user_id: str = Query(default=None),
    days: int = Query(default=90),
):
    """Detect emotional trigger patterns from journal entries.

    Analyzes keyword correlations, time-of-day patterns, and keyword
    co-occurrences to identify what consistently affects the user's mood.
    """
    from services.trigger_detector import detect_triggers

    uid = user_id or settings.default_user_id
    return detect_triggers(uid, days=days)


@router.get("/api/report")
def get_therapist_report(
    user_id: str = Query(default=None),
    days: int = Query(default=14),
):
    """Generate a structured therapist report for the last N days.

    Returns: summary stats, sentiment trend, key entries, drift status,
    coping strategies — everything a therapist needs in one JSON.
    """
    uid = user_id or settings.default_user_id
    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())

    entries = scroll_entries(user_id=uid, date_from=date_from, limit=200)

    if not entries:
        return {"error": "No entries found for this period."}

    # 1. Basic stats
    sentiments = [e.payload.get("sentiment_score", 0) for e in entries]
    avg_sentiment = sum(sentiments) / len(sentiments)
    min_sentiment = min(sentiments)
    max_sentiment = max(sentiments)

    # 2. Sentiment trend by day
    daily_sentiment: dict[str, list[float]] = defaultdict(list)
    for e in entries:
        date = e.payload.get("date", "")
        daily_sentiment[date].append(e.payload.get("sentiment_score", 0))

    sentiment_trend = [
        {"date": d, "avg_sentiment": round(sum(scores) / len(scores), 3), "entries": len(scores)}
        for d, scores in sorted(daily_sentiment.items())
    ]

    # 3. Top keywords
    from collections import Counter as Ctr
    all_kw: list[str] = []
    for e in entries:
        all_kw.extend(e.payload.get("keywords", []))
    kw_counts = Ctr(all_kw)
    top_keywords = [{"word": w, "count": c} for w, c in kw_counts.most_common(10)]

    # 4. Key entries: most negative, most positive, most recent
    sorted_by_sentiment = sorted(entries, key=lambda e: e.payload.get("sentiment_score", 0))

    most_negative = []
    for e in sorted_by_sentiment[:3]:
        most_negative.append({
            "date": e.payload.get("date"),
            "transcript": e.payload.get("transcript", ""),
            "sentiment": e.payload.get("sentiment_score"),
        })

    most_positive = []
    for e in sorted_by_sentiment[-3:]:
        most_positive.append({
            "date": e.payload.get("date"),
            "transcript": e.payload.get("transcript", ""),
            "sentiment": e.payload.get("sentiment_score"),
        })

    # 5. Drift status
    drift = detect_drift(uid)

    # 6. Coping strategies
    coping_entries = search_coping_strategies(user_id=uid, limit=5)
    coping = [
        {"date": e.payload.get("date"), "strategy": e.payload.get("transcript", "")}
        for e in coping_entries
    ]

    return {
        "user_id": uid,
        "period_days": days,
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "summary": {
            "total_entries": len(entries),
            "avg_sentiment": round(avg_sentiment, 3),
            "min_sentiment": round(min_sentiment, 3),
            "max_sentiment": round(max_sentiment, 3),
            "days_with_entries": len(daily_sentiment),
        },
        "sentiment_trend": sentiment_trend,
        "top_keywords": top_keywords,
        "key_entries": {
            "most_negative": most_negative,
            "most_positive": most_positive,
        },
        "drift": {
            "detected": drift.get("detected", False),
            "severity": drift.get("severity", "none"),
            "message": drift.get("message", ""),
            "matching_period": drift.get("matching_period"),
        },
        "coping_strategies": coping,
    }
