"""
Drift Detection Engine.

Algorithm (from PROJECT.md Section 9):
1. RECENT WINDOW: entries from last 7 days → compute centroid
2. BASELINE WINDOW: entries from 8-30 days ago → compute centroid
3. DRIFT SCORE: 1 - cosine_similarity(recent_centroid, baseline_centroid)
4. THRESHOLD: drift_score > 0.25 → DRIFT DETECTED
5. PATTERN MATCHING: if drift detected, search for similar historical periods
6. SEVERITY: 0.25-0.40 mild, 0.40-0.60 moderate, 0.60+ significant

Edge cases:
- < 3 entries in recent window → skip
- < 10 entries in baseline → skip
- Positive drift (sentiment improving) → celebrate
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

from config import settings
from services.qdrant_service import scroll_entries, search_similar, search_coping_strategies


def compute_centroid(vectors: list[list[float]]) -> np.ndarray:
    """Compute the mean vector (centroid) from a list of vectors."""
    arr = np.array(vectors)
    return arr.mean(axis=0)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _severity_label(drift_score: float) -> str:
    """Map drift score to severity label per PROJECT.md."""
    if drift_score >= 0.60:
        return "significant"
    elif drift_score >= 0.40:
        return "moderate"
    elif drift_score >= 0.25:
        return "mild"
    return "none"


def _cluster_dates(dates: list[str]) -> str:
    """Given a list of date strings, return a human-readable date range."""
    if not dates:
        return "unknown period"
    sorted_dates = sorted(dates)
    start = sorted_dates[0]
    end = sorted_dates[-1]
    if start == end:
        return start
    # Format as "Feb 10-17" style
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        if start_dt.month == end_dt.month:
            return f"{start_dt.strftime('%b')} {start_dt.day}-{end_dt.day}"
        return f"{start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d')}"
    except ValueError:
        return f"{start} to {end}"


def detect_drift(user_id: str, new_entry_vector: Optional[list[float]] = None) -> dict:
    """
    Run drift detection for a user.

    Returns a dict with:
      - detected: bool
      - drift_score: float (0 = no drift, up to 2 = max drift)
      - similarity: float (cosine similarity between centroids)
      - severity: str ("none" | "mild" | "moderate" | "significant")
      - message: str (human-readable insight)
      - matching_period: str | None (date range of similar historical period)
      - matching_context: list[str] | None (keywords from matching period)
      - sentiment_direction: str ("declining" | "improving" | "stable")
      - skipped: bool (True if not enough data)
      - skip_reason: str | None
    """
    now = datetime.now(timezone.utc)
    recent_cutoff = int((now - timedelta(days=settings.recent_window_days)).timestamp())
    baseline_start = int((now - timedelta(days=settings.baseline_window_days)).timestamp())
    now_ts = int(now.timestamp())

    # 1. RECENT WINDOW: last 7 days
    recent_entries = scroll_entries(
        user_id=user_id,
        date_from=recent_cutoff,
        date_to=now_ts + 86400,  # include today
        limit=100,
    )

    # Edge case: not enough recent entries
    if len(recent_entries) < 3:
        return {
            "detected": False,
            "drift_score": 0.0,
            "similarity": 1.0,
            "severity": "none",
            "message": "Not enough recent entries for drift detection (need at least 3).",
            "matching_period": None,
            "matching_context": None,
            "sentiment_direction": "stable",
            "skipped": True,
            "skip_reason": f"Only {len(recent_entries)} entries in recent window (need 3+)",
        }

    # 2. BASELINE WINDOW: 8-30 days ago
    baseline_entries = scroll_entries(
        user_id=user_id,
        date_from=baseline_start,
        date_to=recent_cutoff,
        limit=100,
    )

    # Edge case: not enough baseline entries
    if len(baseline_entries) < 10:
        return {
            "detected": False,
            "drift_score": 0.0,
            "similarity": 1.0,
            "severity": "none",
            "message": (
                "Still calibrating — need about 2 weeks of entries "
                "to start noticing patterns."
            ),
            "matching_period": None,
            "matching_context": None,
            "sentiment_direction": "stable",
            "skipped": True,
            "skip_reason": f"Only {len(baseline_entries)} entries in baseline (need 10+)",
        }

    # 3. Compute centroids
    recent_vectors = [e.vector for e in recent_entries]
    baseline_vectors = [e.vector for e in baseline_entries]

    recent_centroid = compute_centroid(recent_vectors)
    baseline_centroid = compute_centroid(baseline_vectors)

    # 4. Drift score
    sim = cosine_similarity(recent_centroid, baseline_centroid)
    drift_score = 1.0 - sim
    severity = _severity_label(drift_score)
    detected = drift_score > settings.drift_threshold

    # 5. Sentiment direction
    recent_sentiments = [e.payload.get("sentiment_score", 0) for e in recent_entries]
    baseline_sentiments = [e.payload.get("sentiment_score", 0) for e in baseline_entries]
    avg_recent_sentiment = sum(recent_sentiments) / len(recent_sentiments)
    avg_baseline_sentiment = sum(baseline_sentiments) / len(baseline_sentiments)

    if avg_recent_sentiment > avg_baseline_sentiment + 0.1:
        sentiment_direction = "improving"
    elif avg_recent_sentiment < avg_baseline_sentiment - 0.1:
        sentiment_direction = "declining"
    else:
        sentiment_direction = "stable"

    # 6. Pattern matching (only if drift detected)
    matching_period = None
    matching_context = None
    coping_strategies = None
    pattern_message = ""

    if detected:
        # Search for historical entries (before baseline) similar to recent centroid
        historical_matches = search_similar(
            vector=recent_centroid.tolist(),
            user_id=user_id,
            limit=5,
            date_before=baseline_start,
        )

        if historical_matches:
            match_dates = [m.payload.get("date", "") for m in historical_matches]
            matching_period = _cluster_dates(match_dates)

            # Collect keywords from matching period
            all_keywords = []
            for m in historical_matches:
                all_keywords.extend(m.payload.get("keywords", []))
            matching_context = list(dict.fromkeys(all_keywords))[:5]

            # Find timestamp range of matching period for coping search
            match_timestamps = [m.payload.get("timestamp", 0) for m in historical_matches]
            match_start = min(match_timestamps) if match_timestamps else 0
            match_end = max(match_timestamps) if match_timestamps else 0

            # Search for coping strategies from the matching period
            # Look in a window around the match (match end + 30 days for recovery)
            if match_end > 0:
                coping_entries = search_coping_strategies(
                    user_id=user_id,
                    date_from=match_start,
                    date_to=match_end + (30 * 86400),
                    limit=3,
                )
                if coping_entries:
                    coping_strategies = [
                        e.payload.get("transcript", "")
                        for e in coping_entries
                    ]

            # Get a representative transcript snippet
            top_transcript = historical_matches[0].payload.get("transcript", "")
            snippet = top_transcript[:100] if top_transcript else ""

            if sentiment_direction == "improving":
                pattern_message = (
                    "You seem to be in a better place than before. "
                    "Your recent entries carry a more positive, hopeful tone."
                )
            else:
                pattern_message = (
                    f"Your recent entries feel similar to how you were "
                    f"around {matching_period}."
                )
                if coping_strategies:
                    # Surface what helped — therapist-style, actionable
                    strategy = coping_strategies[0][:200]
                    pattern_message += (
                        f" Last time you went through this, you found something "
                        f"that helped: \"{strategy}\" — would any of that "
                        f"work for you right now?"
                    )
                elif snippet:
                    pattern_message += (
                        f" Back then you described feeling like this: "
                        f"\"{snippet}...\" — does that resonate?"
                    )
        else:
            if sentiment_direction == "improving":
                pattern_message = (
                    "You seem to be feeling better than your baseline! "
                    "Your recent entries have a more positive tone."
                )
            else:
                pattern_message = (
                    "Your entries feel different from your recent baseline. "
                    "I haven't seen a similar pattern in your earlier entries."
                )

    # Build message
    if not detected:
        message = "Your emotional patterns look steady. Keep checking in — consistency helps build clarity over time."
    else:
        severity_intro = {
            "mild": "I'm noticing a subtle shift in your recent entries.",
            "moderate": "Something seems different in how you've been feeling lately.",
            "significant": "Your recent entries feel quite different from how you were before.",
        }
        message = f"{severity_intro.get(severity, 'I noticed a shift.')} {pattern_message}"

    return {
        "detected": detected,
        "drift_score": round(drift_score, 4),
        "similarity": round(sim, 4),
        "severity": severity,
        "message": message,
        "matching_period": matching_period,
        "matching_context": matching_context,
        "coping_strategies": coping_strategies,
        "sentiment_direction": sentiment_direction,
        "skipped": False,
        "skip_reason": None,
    }
