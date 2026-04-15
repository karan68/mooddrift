"""
Seed 60 demo entries following the narrative arc from PROJECT.md Appendix B.

Periods:
  Jan 15-31 (12): Stable, positive baseline
  Feb 1-9   (6):  Slight stress — transition
  Feb 10-20 (8):  Burnout — first drift event
  Feb 21-28 (5):  Recovery
  Mar 1-31  (15): Stable again — new baseline
  Apr 1-9   (7):  Stable — pre-drift
  Apr 10-14 (7):  New drift — demo trigger

Usage:
  cd backend && python -m seed.seed_data
"""

import sys
import os
import json
import random
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import create_collection, upsert_entry

SEED_USER = settings.default_user_id  # "demo_user"

# --- Entry templates per period ---

ENTRIES = [
    # ===== Jan 15-31: Stable, positive baseline (12 entries) =====
    ("2026-01-15", "Had a really good day at work. Finished a big project milestone and the team celebrated. Feeling accomplished."),
    ("2026-01-16", "Went to the gym after work. The workout felt amazing. I'm sleeping well and eating healthy."),
    ("2026-01-18", "Spent the weekend with friends. We went hiking and it was beautiful outside. Feeling grateful."),
    ("2026-01-19", "Productive Monday. Got through all my tasks and even helped a colleague. Feeling energized."),
    ("2026-01-21", "Had a great lunch with my manager. Got positive feedback on my recent work. Feeling valued."),
    ("2026-01-22", "Cooked a nice dinner at home. Spent the evening reading. Peaceful and content."),
    ("2026-01-24", "Morning jog went well. Hit a new personal record. My energy levels have been consistent."),
    ("2026-01-25", "Team outing today. Good bonding. Work-life balance feels right. Sleeping 7-8 hours."),
    ("2026-01-27", "Wrapped up the week feeling satisfied. No major stressors. Looking forward to the weekend."),
    ("2026-01-28", "Relaxing Sunday. Did some gardening and called family. Feeling grounded and happy."),
    ("2026-01-30", "Started a new side project that I'm excited about. Creative energy is flowing."),
    ("2026-01-31", "End of the month. Overall a great January. Feeling optimistic about February."),

    # ===== Feb 1-9: Slight stress — transition (6 entries) =====
    ("2026-02-01", "Work is picking up. New sprint started with a lot of tickets. Busy but manageable so far."),
    ("2026-02-03", "Had back-to-back meetings all day. Didn't get much actual work done. A bit frustrated but okay."),
    ("2026-02-04", "Deadline moved up by a week. Need to adjust my plans. Feeling slightly pressured."),
    ("2026-02-06", "Working longer hours to catch up. Skipped the gym today. Still manageable though."),
    ("2026-02-07", "Weekend feels short. Spent most of Saturday catching up on work. Mild stress building."),
    ("2026-02-09", "Feeling a bit tired. Sleep quality dropped a little — maybe 6 hours. Nothing alarming yet."),

    # ===== Feb 10-20: Burnout — first drift event (8 entries) =====
    ("2026-02-10", "I'm feeling overwhelmed. The workload is crushing. My manager keeps adding tasks and I can't say no."),
    ("2026-02-11", "Barely slept last night. Maybe 4 hours. My mind won't stop racing about deadlines."),
    ("2026-02-12", "I dread going to work. Every morning I feel this heavy weight. I'm exhausted."),
    ("2026-02-13", "Snapped at a colleague today. I never do that. I'm not myself. Can't concentrate."),
    ("2026-02-15", "Weekend but I couldn't relax. Kept thinking about Monday. Skipped meals. Feeling anxious."),
    ("2026-02-16", "Headaches are becoming frequent. I know it's stress. Everything feels like too much."),
    ("2026-02-18", "Called in sick today. I just couldn't face it. Stayed in bed most of the day. Feel guilty."),
    ("2026-02-20", "Hit rock bottom this week. I told my manager I need help. She was understanding. Maybe things will change."),

    # ===== Feb 21-28: Recovery (5 entries + 2 coping strategies) =====
    ("2026-02-21", "Took a mental health day. Went for a long walk. Starting to feel a tiny bit better."),
    ("2026-02-23", "Manager redistributed some tasks. Workload is lighter. Slept 6 hours. Small improvement."),
    ("2026-02-24", "Went back to the gym for the first time in weeks. It was hard but I did it. Feeling hopeful."),
    ("2026-02-26", "Taking things one day at a time. Set boundaries at work — leaving at 6pm. Feeling more in control."),
    ("2026-02-28", "End of February. Recovery is happening. I learned that taking a weekend completely offline helps reset things."),
    # Coping strategies — tagged separately
    ("2026-02-27", "COPING: What helped me recover from burnout — taking a full weekend completely offline, no laptop no emails. Also going back to the gym and setting a hard boundary to leave work by 6pm every day."),
    ("2026-02-28", "COPING: Telling my manager I was struggling was the turning point. She redistributed tasks and I felt heard. Speaking up and asking for help was the hardest but most important thing."),

    # ===== Mar 1-31: Stable again — new baseline (15 entries) =====
    ("2026-03-01", "Fresh month, fresh start. Work is manageable again. Feeling cautiously optimistic."),
    ("2026-03-03", "Good productive day. Completed my tasks on time. No overtime. Feeling balanced."),
    ("2026-03-05", "Morning meditation is helping. Sleep is back to 7 hours. Energy levels improving."),
    ("2026-03-07", "Weekend hike with friends. Nature recharges me. Feeling grateful for support."),
    ("2026-03-09", "Work review went well. Manager acknowledged my recovery. Team is supportive."),
    ("2026-03-11", "Started a new hobby — cooking new recipes. It's relaxing and creative."),
    ("2026-03-13", "Steady week. No major highs or lows. That's exactly what I need right now."),
    ("2026-03-15", "Mid-month check. Everything feels stable. Sleep good, appetite good, mood good."),
    ("2026-03-17", "Celebrated a friend's birthday. Social connections feel strong. Laughed a lot."),
    ("2026-03-19", "Productive sprint review. My contributions were recognized. Feeling valued."),
    ("2026-03-21", "Spring is here. Went for evening walks this week. Mood is consistently positive."),
    ("2026-03-23", "Weekend was relaxing. Read a book, cooked, watched a movie. Simple pleasures."),
    ("2026-03-25", "Team lunch today. Workplace feels healthy again. Glad I spoke up in February."),
    ("2026-03-28", "Yoga class twice this week. Body and mind feel connected. Sleeping 7-8 hours."),
    ("2026-03-31", "End of March. Two great weeks in a row. Feeling strong and resilient."),

    # ===== Apr 1-9: Stable — pre-drift (7 entries) =====
    ("2026-04-01", "April begins well. Work is steady. New quarter goals are clear and achievable."),
    ("2026-04-02", "Good gym session. Eating well. Social life is active. Feeling balanced."),
    ("2026-04-04", "Completed a challenging task ahead of schedule. Feeling confident and capable."),
    ("2026-04-05", "Relaxing weekend. Brunch with friends. Walked in the park. Life feels good."),
    ("2026-04-07", "Monday went smoothly. No surprises. Steady and predictable — just right."),
    ("2026-04-08", "Team stand-up was positive. Sprint is on track. Energy is good."),
    ("2026-04-09", "Mid-week and all is well. Looking forward to the weekend. Feeling content."),

    # ===== Apr 10-14: New drift — demo trigger (7 entries) =====
    ("2026-04-10", "New deadline dropped out of nowhere. The client wants everything by Friday. Starting to feel pressured."),
    ("2026-04-11", "Worked until midnight. Skipped dinner. The scope keeps changing and I can't keep up."),
    ("2026-04-12", "Barely slept. Maybe 4 hours again. My anxiety is spiking. This feels familiar."),
    ("2026-04-13", "I'm overwhelmed again. The pressure is mounting and I can feel myself slipping. Skipping meals."),
    ("2026-04-13", "Can't focus. Every task feels impossible. My heart races when I open my laptop."),
    ("2026-04-14", "This is like February all over again. Deadline pressure, no sleep, dread. I need to do something before it gets worse."),
    ("2026-04-14", "Feeling anxious and exhausted. I recognize this pattern now. Maybe I should take that weekend off like last time."),
]


def seed():
    """Seed all entries into Qdrant."""
    print(f"Creating collection '{settings.collection_name}'...")
    create_collection()

    print(f"\nSeeding {len(ENTRIES)} entries for user '{SEED_USER}'...")

    for i, (date_str, transcript) in enumerate(ENTRIES):
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=random.randint(8, 20),
            minute=random.randint(0, 59),
            tzinfo=timezone.utc,
        )

        # Detect coping strategy entries
        is_coping = transcript.startswith("COPING:")
        clean_transcript = transcript.replace("COPING: ", "") if is_coping else transcript

        vector = generate_embedding(clean_transcript)
        sentiment = analyze_sentiment(clean_transcript)
        keywords = extract_keywords(clean_transcript)

        payload = {
            "user_id": SEED_USER,
            "date": date_str,
            "timestamp": int(dt.timestamp()),
            "transcript": clean_transcript,
            "sentiment_score": sentiment,
            "keywords": keywords,
            "week_number": dt.isocalendar()[1],
            "month": dt.strftime("%Y-%m"),
            "entry_type": "coping_strategy" if is_coping else "checkin",
        }

        point_id = upsert_entry(vector, payload)
        tag = " [COPING]" if is_coping else ""
        print(f"  [{i+1:2d}/{len(ENTRIES)}] {date_str} | sentiment={sentiment:+.2f} | {point_id[:8]}...{tag}")

    print(f"\nDone! Seeded {len(ENTRIES)} entries.")


if __name__ == "__main__":
    seed()
