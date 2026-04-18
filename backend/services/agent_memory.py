"""
Agent Memory — FEATURES.md Feature 5.

Builds rich context from a user's journal history so the voice agent
and Telegram bot can reference past entries, follow up on themes, and
acknowledge emotional arcs.

The key insight: a stateless agent says "How are you feeling?"
An agent with memory says "Last time you mentioned deadline pressure
was getting to you — how did that go?"
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional


def build_agent_context(user_id: str) -> dict:
    """Assemble the user's recent context for agent injection.

    Pulls from Qdrant:
      - Last 5 entries (transcripts, sentiment, keywords)
      - Current drift status
      - Top triggers
      - Available time capsules

    Returns a structured dict that can be serialized to JSON for Vapi
    or used directly by the Telegram bot.
    """
    from services.qdrant_service import scroll_entries
    from services.drift_engine import detect_drift

    now = datetime.now(timezone.utc)

    # === 1. Recent entries (last 14 days, up to 10) ===
    date_from = int((now - timedelta(days=14)).timestamp())
    raw_entries = scroll_entries(user_id=user_id, date_from=date_from, limit=20)

    # Filter out time capsules
    entries = [
        e for e in raw_entries
        if (e.payload or {}).get("entry_type") != "time_capsule"
    ]

    # Sort by timestamp descending (most recent first)
    entries.sort(key=lambda e: e.payload.get("timestamp", 0), reverse=True)
    recent = entries[:5]

    if not recent:
        return {
            "has_context": False,
            "message": "No recent journal entries found.",
            "last_entry": None,
            "recent_themes": [],
            "sentiment_trend": "unknown",
            "drift_status": "no_data",
            "triggers": [],
            "has_capsule": False,
            "entry_count_14d": 0,
        }

    # === 2. Last entry details ===
    last = recent[0].payload
    last_entry = {
        "date": last.get("date"),
        "transcript": (last.get("transcript") or "")[:200],
        "sentiment": last.get("sentiment_score", 0.0),
        "keywords": last.get("keywords", []),
    }

    # === 3. Recent themes (keyword frequency across last 14 days) ===
    all_keywords: list[str] = []
    sentiments: list[float] = []
    for e in entries[:10]:
        p = e.payload or {}
        all_keywords.extend(p.get("keywords", []))
        sentiments.append(p.get("sentiment_score", 0.0))

    kw_counts = Counter(all_keywords)
    recent_themes = [kw for kw, count in kw_counts.most_common(5) if count >= 2]

    # === 4. Sentiment trend ===
    if len(sentiments) >= 4:
        first_half = sentiments[len(sentiments) // 2:]  # older half
        second_half = sentiments[:len(sentiments) // 2]  # newer half
        avg_old = sum(first_half) / len(first_half)
        avg_new = sum(second_half) / len(second_half)
        if avg_new > avg_old + 0.1:
            sentiment_trend = "improving"
        elif avg_new < avg_old - 0.1:
            sentiment_trend = "declining"
        else:
            sentiment_trend = "stable"
        trend_detail = f"from {avg_old:.2f} to {avg_new:.2f}"
    else:
        sentiment_trend = "not_enough_data"
        trend_detail = ""

    # === 5. Drift status ===
    drift = detect_drift(user_id)
    drift_status = "stable"
    drift_message = ""
    if drift.get("skipped"):
        drift_status = "calibrating"
    elif drift.get("detected"):
        drift_status = drift.get("severity", "mild")
        drift_message = drift.get("message", "")

    # === 6. Top triggers (if available) ===
    triggers = []
    try:
        from services.trigger_detector import detect_triggers
        trigger_result = detect_triggers(user_id, days=90)
        neg = [t for t in trigger_result.get("keyword_triggers", []) if t["impact"] < 0][:2]
        pos = [t for t in trigger_result.get("keyword_triggers", []) if t["impact"] > 0][:2]
        triggers = [
            {"word": t["trigger"], "impact": t["impact"], "type": "negative"}
            for t in neg
        ] + [
            {"word": t["trigger"], "impact": t["impact"], "type": "positive"}
            for t in pos
        ]
    except Exception:
        pass

    # === 7. Capsules ===
    has_capsule = False
    try:
        from services.time_capsule import find_capsules_for_drift
        capsules = find_capsules_for_drift(user_id, days=180)
        has_capsule = len(capsules) > 0
    except Exception:
        pass

    # === 8. Recurring themes (things mentioned in 2+ recent entries) ===
    recurring = []
    if len(entries) >= 2:
        last_kws = set(entries[0].payload.get("keywords", []))
        prev_kws = set(entries[1].payload.get("keywords", []))
        shared = last_kws & prev_kws
        if shared:
            recurring = list(shared)[:3]

    return {
        "has_context": True,
        "last_entry": last_entry,
        "recent_themes": recent_themes,
        "recurring_themes": recurring,
        "sentiment_trend": sentiment_trend,
        "trend_detail": trend_detail,
        "drift_status": drift_status,
        "drift_message": drift_message,
        "triggers": triggers,
        "has_capsule": has_capsule,
        "entry_count_14d": len(entries),
        "avg_sentiment_14d": round(sum(sentiments) / len(sentiments), 3) if sentiments else 0.0,
    }


def format_context_for_vapi(context: dict) -> str:
    """Convert the context dict into a natural-language string for injection
    into the Vapi agent's function call response.

    The agent reads this and weaves it into conversation naturally.
    """
    if not context.get("has_context"):
        return "This is a new user with no previous entries. Start fresh — ask how they're feeling today."

    parts = []

    # Last entry
    last = context["last_entry"]
    if last:
        parts.append(
            f"Their last check-in was on {last['date']}. "
            f"They said: \"{last['transcript']}\""
        )
        if last["keywords"]:
            parts.append(f"Main themes were: {', '.join(last['keywords'][:3])}")

    # Recurring themes
    if context.get("recurring_themes"):
        parts.append(
            f"They keep mentioning: {', '.join(context['recurring_themes'])}. "
            "This seems to be on their mind."
        )

    # Sentiment trend
    if context["sentiment_trend"] == "improving":
        parts.append(
            f"Their mood has been improving recently ({context.get('trend_detail', '')})."
        )
    elif context["sentiment_trend"] == "declining":
        parts.append(
            f"Their mood has been declining recently ({context.get('trend_detail', '')}). "
            "Be gentle."
        )

    # Drift
    if context["drift_status"] not in ("stable", "calibrating", "no_data"):
        parts.append(f"DRIFT DETECTED ({context['drift_status']}). {context['drift_message']}")

    # Triggers
    neg_triggers = [t for t in context.get("triggers", []) if t["type"] == "negative"]
    pos_triggers = [t for t in context.get("triggers", []) if t["type"] == "positive"]
    if neg_triggers:
        words = ", ".join(t["word"] for t in neg_triggers)
        parts.append(f"Known negative triggers: {words}")
    if pos_triggers:
        words = ", ".join(t["word"] for t in pos_triggers)
        parts.append(f"Known positive triggers: {words}")

    # Capsule
    if context.get("has_capsule"):
        parts.append("They have a time capsule recorded from a positive period.")

    # Entry count
    parts.append(f"They've checked in {context['entry_count_14d']} times in the last 2 weeks.")

    return " ".join(parts)


def format_context_for_telegram(context: dict, current_sentiment: float) -> Optional[str]:
    """Generate a context-aware reply addition for Telegram.

    Returns a short message that references past entries, or None if
    nothing noteworthy to add.
    """
    if not context.get("has_context"):
        return None

    parts = []

    # Recurring themes
    recurring = context.get("recurring_themes", [])
    if recurring:
        theme_str = ", ".join(recurring[:2])
        parts.append(f"You've been mentioning _{theme_str}_ a lot lately.")

    # Sentiment trend
    last = context.get("last_entry")
    if last:
        last_sent = last.get("sentiment", 0.0)
        if current_sentiment > last_sent + 0.3:
            parts.append("Your tone feels lighter than last time. That's good to see.")
        elif current_sentiment < last_sent - 0.3:
            parts.append("This feels heavier than your last check-in. I'm here.")

    # Triggers warning
    neg_triggers = [t for t in context.get("triggers", []) if t["type"] == "negative"]
    if neg_triggers:
        # Check if current entry keywords match a known trigger
        # (can't check here without current keywords, so skip)
        pass

    if not parts:
        return None

    return "\n".join(parts)
