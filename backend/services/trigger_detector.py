"""
Trigger Pattern Detection — FEATURES.md Feature 3.

Analyzes journal entries to identify consistent emotional triggers:
  - Keyword triggers: topics that correlate with lower/higher sentiment
  - Time-of-day triggers: time buckets with consistently different sentiment
  - Co-occurrence triggers: keyword pairs that together worsen sentiment

The key insight: drift detection tells you THAT you shifted.
Trigger detection tells you WHY.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from itertools import combinations

# Noise words that are too generic to be meaningful triggers.
# These frequently appear but carry no actionable insight.
_NOISE_WORDS = {
    "today", "went", "feeling", "feel", "felt", "really", "going", "getting",
    "thing", "things", "much", "just", "like", "also", "still", "even",
    "good", "well", "got", "make", "made", "time", "lot", "back", "way",
    "day", "week", "little", "bit", "want", "need", "know", "think",
    "one", "two", "would", "could", "something", "anything", "everything",
    "last", "first", "new", "come", "take", "start", "keep", "try",
    "right", "long", "get", "see", "able", "since", "around", "every",
    "many", "thought", "said", "told", "asked", "let", "put", "set",
    "maybe", "might", "however", "although", "though", "enough", "part",
}

# Minimum occurrences for a keyword to be considered as a potential trigger.
_MIN_KEYWORD_OCCURRENCES = 3

# Minimum sentiment difference to flag as a trigger.
_MIN_KEYWORD_IMPACT = 0.2

# Minimum occurrences for a co-occurrence pair.
_MIN_COOCCURRENCE = 3

# Minimum additional impact for a co-occurrence (beyond individual keywords).
_MIN_COOCCURRENCE_EXTRA_IMPACT = 0.15

# Time-of-day bucket boundaries (hour ranges).
_TIME_BUCKETS = {
    "Morning (6AM–12PM)": (6, 12),
    "Afternoon (12PM–5PM)": (12, 17),
    "Evening (5PM–9PM)": (17, 21),
    "Night (9PM–2AM)": (21, 26),  # 26 = wraps to 2AM next day
}

# Minimum entries in a time bucket to consider it.
_MIN_TIME_BUCKET_ENTRIES = 3

# Minimum sentiment deviation from overall avg for a time trigger.
_MIN_TIME_IMPACT = 0.15


def _classify_confidence(occurrences: int, impact: float) -> str:
    """Assign a confidence level based on evidence strength."""
    if occurrences >= 8 and abs(impact) >= 0.3:
        return "high"
    if occurrences >= 5 and abs(impact) >= 0.2:
        return "medium"
    return "low"


def _get_hour(timestamp: int) -> int:
    """Extract hour (0-23) from a Unix timestamp."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).hour


def detect_triggers(user_id: str, days: int = 90) -> dict:
    """Run full trigger analysis for a user.

    Returns:
        {
          "keyword_triggers": [...],
          "time_triggers": [...],
          "cooccurrence_triggers": [...],
          "total_entries_analyzed": int,
          "analysis_window_days": int,
        }
    """
    from services.qdrant_service import scroll_entries

    now = datetime.now(timezone.utc)
    date_from = int((now - timedelta(days=days)).timestamp())
    raw_entries = scroll_entries(user_id=user_id, date_from=date_from, limit=500)

    # Filter out time capsules — they're not regular journal entries
    entries = [
        e for e in raw_entries
        if (e.payload or {}).get("entry_type") != "time_capsule"
    ]

    if len(entries) < 5:
        return {
            "keyword_triggers": [],
            "time_triggers": [],
            "cooccurrence_triggers": [],
            "total_entries_analyzed": len(entries),
            "analysis_window_days": days,
        }

    keyword_triggers = _detect_keyword_triggers(entries)
    time_triggers = _detect_time_triggers(entries)
    cooccurrence_triggers = _detect_cooccurrence_triggers(entries)

    return {
        "keyword_triggers": keyword_triggers,
        "time_triggers": time_triggers,
        "cooccurrence_triggers": cooccurrence_triggers,
        "total_entries_analyzed": len(entries),
        "analysis_window_days": days,
    }


def _detect_keyword_triggers(entries: list) -> list[dict]:
    """Find keywords whose presence correlates with sentiment shifts.

    For each keyword appearing 3+ times:
      - avg_sentiment_with: average sentiment when keyword is present
      - avg_sentiment_without: average sentiment when keyword is absent
      - impact: difference (with - without). Negative = keyword drags mood down.
    """
    all_sentiments = [e.payload.get("sentiment_score", 0.0) for e in entries]
    overall_avg = sum(all_sentiments) / len(all_sentiments)

    # Count keyword occurrences and gather sentiment per keyword
    kw_data: dict[str, list[float]] = {}
    for e in entries:
        payload = e.payload or {}
        sentiment = payload.get("sentiment_score", 0.0)
        keywords = payload.get("keywords", [])
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in _NOISE_WORDS:
                continue
            if len(kw_lower) < 3:
                continue
            kw_data.setdefault(kw_lower, []).append(sentiment)

    triggers = []
    total = len(entries)

    for kw, sentiments_with in kw_data.items():
        count = len(sentiments_with)
        if count < _MIN_KEYWORD_OCCURRENCES:
            continue

        avg_with = sum(sentiments_with) / count
        # Compute avg WITHOUT this keyword
        sum_without = sum(all_sentiments) - sum(sentiments_with)
        count_without = total - count
        if count_without == 0:
            continue
        avg_without = sum_without / count_without

        impact = avg_with - avg_without

        if abs(impact) < _MIN_KEYWORD_IMPACT:
            continue

        triggers.append({
            "type": "keyword",
            "trigger": kw,
            "avg_sentiment_with": round(avg_with, 3),
            "avg_sentiment_without": round(avg_without, 3),
            "impact": round(impact, 3),
            "occurrences": count,
            "confidence": _classify_confidence(count, impact),
        })

    # Sort by absolute impact (strongest triggers first)
    triggers.sort(key=lambda t: abs(t["impact"]), reverse=True)
    return triggers


def _detect_time_triggers(entries: list) -> list[dict]:
    """Find time-of-day buckets with consistently different sentiment.

    Buckets: Morning (6-12), Afternoon (12-17), Evening (17-21), Night (21-2).
    Only flags if a bucket deviates from overall avg by > threshold.
    """
    all_sentiments = [e.payload.get("sentiment_score", 0.0) for e in entries]
    overall_avg = sum(all_sentiments) / len(all_sentiments)

    # Bucket entries by time of day
    buckets: dict[str, list[float]] = {name: [] for name in _TIME_BUCKETS}

    for e in entries:
        payload = e.payload or {}
        ts = payload.get("timestamp")
        if ts is None:
            continue
        hour = _get_hour(ts)

        for name, (start, end) in _TIME_BUCKETS.items():
            if end <= 24:
                if start <= hour < end:
                    buckets[name].append(payload.get("sentiment_score", 0.0))
                    break
            else:
                # Wraps past midnight (e.g., Night 21-26 → 21-24 + 0-2)
                if hour >= start or hour < (end - 24):
                    buckets[name].append(payload.get("sentiment_score", 0.0))
                    break

    triggers = []
    for name, sentiments in buckets.items():
        if len(sentiments) < _MIN_TIME_BUCKET_ENTRIES:
            continue

        bucket_avg = sum(sentiments) / len(sentiments)
        impact = bucket_avg - overall_avg

        if abs(impact) < _MIN_TIME_IMPACT:
            continue

        triggers.append({
            "type": "time",
            "trigger": name,
            "avg_sentiment": round(bucket_avg, 3),
            "baseline_avg": round(overall_avg, 3),
            "impact": round(impact, 3),
            "occurrences": len(sentiments),
            "confidence": _classify_confidence(len(sentiments), impact),
        })

    triggers.sort(key=lambda t: abs(t["impact"]), reverse=True)
    return triggers


def _detect_cooccurrence_triggers(entries: list) -> list[dict]:
    """Find keyword PAIRS that together worsen sentiment beyond either alone.

    For each pair (A, B) appearing together 3+ times:
      - avg_sentiment_together: avg when both A and B are in the entry
      - avg_sentiment_apart: avg when only one of A or B is present
      - If together is significantly worse than apart → flag
    """
    # Build per-entry keyword sets (filtered)
    entry_kw_sets: list[tuple[set[str], float]] = []
    for e in entries:
        payload = e.payload or {}
        keywords = {
            kw.lower() for kw in payload.get("keywords", [])
            if kw.lower() not in _NOISE_WORDS and len(kw) >= 3
        }
        if keywords:
            entry_kw_sets.append((keywords, payload.get("sentiment_score", 0.0)))

    # Find all keywords that appear at least _MIN_COOCCURRENCE times
    kw_counts: dict[str, int] = {}
    for kws, _ in entry_kw_sets:
        for kw in kws:
            kw_counts[kw] = kw_counts.get(kw, 0) + 1

    frequent_kws = [kw for kw, c in kw_counts.items() if c >= _MIN_COOCCURRENCE]

    if len(frequent_kws) < 2:
        return []

    # For each pair of frequent keywords, check co-occurrence stats
    triggers = []

    for kw_a, kw_b in combinations(frequent_kws, 2):
        together_sentiments = []
        only_a_sentiments = []
        only_b_sentiments = []

        for kws, sentiment in entry_kw_sets:
            has_a = kw_a in kws
            has_b = kw_b in kws
            if has_a and has_b:
                together_sentiments.append(sentiment)
            elif has_a:
                only_a_sentiments.append(sentiment)
            elif has_b:
                only_b_sentiments.append(sentiment)

        if len(together_sentiments) < _MIN_COOCCURRENCE:
            continue

        avg_together = sum(together_sentiments) / len(together_sentiments)

        # "Apart" = entries with A-only or B-only (not both)
        apart = only_a_sentiments + only_b_sentiments
        if not apart:
            continue
        avg_apart = sum(apart) / len(apart)

        # The co-occurrence impact: how much worse is the pair together vs apart
        extra_impact = avg_together - avg_apart

        if abs(extra_impact) < _MIN_COOCCURRENCE_EXTRA_IMPACT:
            continue

        triggers.append({
            "type": "co-occurrence",
            "trigger": f"{kw_a} + {kw_b}",
            "keywords": [kw_a, kw_b],
            "avg_sentiment_together": round(avg_together, 3),
            "avg_sentiment_apart": round(avg_apart, 3),
            "impact": round(extra_impact, 3),
            "occurrences": len(together_sentiments),
            "confidence": _classify_confidence(len(together_sentiments), extra_impact),
        })

    triggers.sort(key=lambda t: abs(t["impact"]), reverse=True)
    return triggers[:10]  # Cap at 10 co-occurrence triggers
