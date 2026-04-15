"""
Seed multiple user profiles with diverse emotional arcs.

Profiles:
  1. demo_user     — Working professional, burnout arc (existing)
  2. student_ananya — College student, exam anxiety → social isolation → finding balance
  3. parent_rahul   — New parent, sleep deprivation + joy, relationship strain
  4. athlete_priya  — Athlete, injury → frustration → rehab progress → comeback anxiety

Usage:
  cd backend && python -m seed.seed_profiles
"""

import sys
import os
import random
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.embedding import generate_embedding
from services.sentiment import analyze_sentiment
from services.keywords import extract_keywords
from services.qdrant_service import create_collection, upsert_entry

# =====================================================================
# PROFILE 2: student_ananya — Exam stress → isolation → balance
# =====================================================================
STUDENT_ENTRIES = [
    # Jan 15-31: Confident start of semester (10)
    ("2026-01-15", "First day of the new semester. I'm taking some tough courses but I feel ready. Met my study group today."),
    ("2026-01-17", "Great lecture on machine learning today. I understood everything. Feeling smart and motivated."),
    ("2026-01-19", "Went to a college fest with friends. Danced, laughed, ate too much. Life feels good."),
    ("2026-01-21", "Submitted my first assignment early. Professor said it was well done. Confidence boost."),
    ("2026-01-23", "Study group session went well. We're all on the same page. Coffee and coding — perfect day."),
    ("2026-01-25", "Weekend trip to the lake with roommates. Disconnected from everything. Came back refreshed."),
    ("2026-01-27", "Aced the pop quiz today. All those study sessions are paying off. Feeling proud."),
    ("2026-01-28", "Called mom and dad. They're proud of my grades. That felt really good."),
    ("2026-01-30", "Joined a new coding club. Met interesting people. Feeling like I belong here."),
    ("2026-01-31", "Good month overall. Balanced academics and social life. Sleeping well, eating well."),

    # Feb 1-8: Midterms approaching, slight pressure (5)
    ("2026-02-01", "Midterm schedule released. Five exams in two weeks. Starting to feel the pressure."),
    ("2026-02-03", "Skipped the coding club meeting to study. Miss my friends but priorities."),
    ("2026-02-05", "Studying 8 hours a day now. My back hurts from sitting. But I need to keep going."),
    ("2026-02-06", "Study group cancelled because everyone is stressed. We're all in survival mode."),
    ("2026-02-08", "Haven't been outside in 3 days. Just my room, books, and instant noodles."),

    # Feb 10-22: Exam anxiety spiral, isolation (9)
    ("2026-02-10", "First midterm tomorrow. I can't remember anything. My mind goes blank when I try to recall formulas. Panicking."),
    ("2026-02-11", "Exam went badly. I froze during the math section. Couldn't write anything for 20 minutes. Feel like a failure."),
    ("2026-02-12", "Can't eat. Can't sleep. Next exam is in 2 days and I haven't started. What's wrong with me?"),
    ("2026-02-14", "Everyone else seems fine. They're posting Valentine's Day photos while I'm crying over textbooks. Feeling so alone."),
    ("2026-02-15", "Skipped another exam prep session because I had a panic attack. My hands were shaking."),
    ("2026-02-17", "Mom called and I lied and said everything is fine. I don't want to worry her. But I'm not fine."),
    ("2026-02-18", "Haven't talked to my roommates in a week. I just stay in my room. They knocked but I said I was studying."),
    ("2026-02-20", "Third exam done. I think I failed. I don't even care anymore. I just want this to be over."),
    ("2026-02-22", "Broke down crying in the library today. A stranger asked if I was okay. That made me cry harder."),

    # Feb 23-28: Reaching out, small recovery (4)
    ("2026-02-23", "Finally told my roommate how I've been feeling. She hugged me and said she felt the same way. We're not alone."),
    ("2026-02-25", "Went to the campus counselor. She was kind. Said anxiety during exams is normal but I should talk about it. Felt lighter."),
    ("2026-02-26", "Study group resumed. We studied together and ordered pizza. Forgot about stress for a few hours."),
    ("2026-02-28", "Last midterm done. Results don't matter right now. I survived. Going to sleep for 12 hours."),

    # Mar 1-31: Recovery and balance (12)
    ("2026-03-01", "Slept 10 hours. Woke up feeling human again. Went for a walk in the sun."),
    ("2026-03-03", "Midterm results came. I passed everything. Not amazing grades but I didn't fail. Relief."),
    ("2026-03-05", "Back to coding club. Everyone welcomed me back. Felt warm inside."),
    ("2026-03-08", "Started doing morning walks. 20 minutes before class. It clears my head."),
    ("2026-03-10", "Had an honest call with mom. Told her about the anxiety. She was understanding. Weight off my shoulders."),
    ("2026-03-13", "Study group has a rule now — we take breaks every 90 minutes. No one is allowed to skip meals."),
    ("2026-03-15", "Went to a movie with friends. First time in weeks I laughed without guilt."),
    ("2026-03-18", "Counselor says I'm making progress. She taught me breathing exercises. They actually work."),
    ("2026-03-21", "Submitted a project I'm genuinely proud of. Not just for grades — I learned something."),
    ("2026-03-24", "Weekend picnic with the whole friend group. We talked about mental health openly. Everyone has struggled."),
    ("2026-03-27", "Sleeping 7-8 hours now. Eating properly. Exercise 3 times a week. Feeling balanced."),
    ("2026-03-31", "End of March. I'm in a much better place. I know what my warning signs look like now."),

    # Apr 1-9: Stable (5)
    ("2026-04-01", "New month. Finals are next month but I'm not panicking yet. Taking it day by day."),
    ("2026-04-03", "Good study session. Understood a difficult concept. Asked questions in class for the first time."),
    ("2026-04-05", "Weekend with friends. Board games and chai. Simple joys."),
    ("2026-04-07", "Professor offered me a research position. I'm considering it. Feeling excited about learning again."),
    ("2026-04-09", "Consistent routine. Study, exercise, friends, sleep. This is sustainable."),

    # Apr 10-14: Finals approaching — early warning signs (5)
    ("2026-04-10", "Finals schedule released. Six exams. My stomach dropped when I saw it. Here we go again."),
    ("2026-04-11", "Started studying but can't focus. My mind keeps drifting to worst-case scenarios. What if I freeze again?"),
    ("2026-04-12", "Skipped morning walk to study. Ate instant noodles for dinner. I know these are bad signs."),
    ("2026-04-13", "Couldn't sleep last night. Kept revising in my head. My roommate asked if I'm okay. I said yes but I'm not sure."),
    ("2026-04-14", "The anxiety is creeping back. Same feeling as February. I need to talk to someone before it spirals."),
]

# =====================================================================
# PROFILE 3: parent_rahul — New parent, exhaustion + joy
# =====================================================================
PARENT_ENTRIES = [
    # Jan 15-31: Baby's first weeks, overwhelmed but happy (10)
    ("2026-01-15", "Baby is 3 weeks old. I didn't know love could feel this intense. Also didn't know sleep deprivation could feel this brutal."),
    ("2026-01-17", "Up four times last night. The baby won't stop crying unless I hold her. My arms are sore but her face is everything."),
    ("2026-01-19", "First smile today. Or was it gas? Either way, I melted. Then changed three diapers in an hour."),
    ("2026-01-21", "Priya and I argued about who's more tired. We're both exhausted. Need to be kinder to each other."),
    ("2026-01-23", "Mom came to visit. She took care of the baby for 4 hours. I slept and it felt like heaven."),
    ("2026-01-25", "Baby slept 3 hours straight for the first time. I woke up in a panic thinking something was wrong. She was fine. I am not."),
    ("2026-01-27", "Work wants me back next week. How do I leave this tiny human? How do people do this?"),
    ("2026-01-28", "Read a parenting book. It says to sleep when the baby sleeps. The baby sleeps for 45 minutes. That's not sleep."),
    ("2026-01-30", "Took the baby for a walk in the park. Sun on my face, baby in the carrier. Felt peaceful for the first time in weeks."),
    ("2026-01-31", "One month of being a dad. Hardest thing I've ever done. Best thing I've ever done."),

    # Feb 1-9: Return to work, guilt and exhaustion (6)
    ("2026-02-01", "First day back at work. Kept checking the baby monitor app every 10 minutes. Couldn't concentrate."),
    ("2026-02-03", "Came home to a screaming baby and a crying wife. She said she can't do this alone. I feel guilty for working."),
    ("2026-02-05", "Boss asked why my productivity is down. I almost said 'I slept 3 hours.' Instead I smiled and said I'd catch up."),
    ("2026-02-06", "Priya and I haven't had a real conversation in days. Just handoffs. Baby logistics. I miss us."),
    ("2026-02-08", "Fell asleep during a meeting. My colleague covered for me. Grateful but embarrassed."),
    ("2026-02-09", "Weekend but there's no weekend with a baby. Every day is the same loop. Feed, burp, change, sleep, repeat."),

    # Feb 10-20: Breaking point, relationship strain (8)
    ("2026-02-10", "Big fight with Priya. She said I don't help enough. I said I'm working full time. We both cried. The baby cried."),
    ("2026-02-12", "Haven't seen my friends in 6 weeks. They invited me out and I couldn't go. Feeling isolated."),
    ("2026-02-13", "Baby got sick. Rushed to the doctor at 2am. She's fine but I thought the worst. My hands are still shaking."),
    ("2026-02-15", "I love my daughter more than anything. But I hate that I've become this tired, irritable version of myself."),
    ("2026-02-16", "Burned dinner because I was rocking the baby. Ordered takeout again. We used to cook together every night."),
    ("2026-02-18", "Priya said she feels invisible. I feel invisible too. We're both drowning and can't help each other."),
    ("2026-02-19", "Caught myself snapping at Priya over nothing. I'm turning into someone I don't like."),
    ("2026-02-20", "Took a sick day just to sleep. Felt guilty the entire time. You're not supposed to need a break from your own child."),

    # Feb 21-28: Getting help, small improvements (5)
    ("2026-02-21", "Priya and I had a real talk. We agreed to ask for help. Called her parents. They're coming next week."),
    ("2026-02-23", "In-laws arrived. Someone else is holding the baby. Priya and I had dinner together for the first time in a month."),
    ("2026-02-25", "Slept 7 hours last night. I forgot what rested feels like. It's like a superpower."),
    ("2026-02-26", "Went for a run for the first time since the baby was born. My body ached but my mind felt clear."),
    ("2026-02-28", "Priya and I went on a date. Just coffee for an hour while her mom watched the baby. We held hands. We're going to be okay."),

    # Mar 1-31: Finding rhythm (12)
    ("2026-03-01", "Started a shift system with Priya. I do nights on weekdays, she does weekends. It's working."),
    ("2026-03-04", "Baby laughed for the first time. A real laugh. I recorded it and watched it 50 times."),
    ("2026-03-07", "Joined an online dads group. Turns out everyone feels like a fraud. That's oddly comforting."),
    ("2026-03-10", "Work is easier now. I'm not checking the monitor as much. Trust is building."),
    ("2026-03-12", "Priya and I are communicating better. We have a weekly check-in now. 15 minutes to just talk about us."),
    ("2026-03-15", "Baby is sleeping 5-hour stretches. This changes everything. I feel human again."),
    ("2026-03-18", "Took the baby to meet my friends. They were amazing with her. I didn't realize how much I missed them."),
    ("2026-03-21", "Figured out that baby carrier walks are my meditation. 30 minutes of walking and thinking."),
    ("2026-03-24", "Priya went out with her friends tonight. I handled bedtime alone and it went great. Proud dad moment."),
    ("2026-03-27", "Three months old. She recognizes my face now. Reaches for me. My heart is full."),
    ("2026-03-29", "Getting a routine down. Work, baby, exercise, couple time. Not perfect but functional."),
    ("2026-03-31", "Best month yet. We found our rhythm. I stopped expecting perfection and started accepting good enough."),

    # Apr 1-9: Stable and happy (5)
    ("2026-04-01", "Good morning routine now. Baby, coffee, 10-minute meditation. Starting days with calm."),
    ("2026-04-03", "Performance review at work went well. Boss said he noticed the improvement. Felt validated."),
    ("2026-04-05", "Family photo day. Baby in a tiny dress. Priya laughing. My favorite picture ever."),
    ("2026-04-07", "Started planning a weekend getaway for our anniversary. In-laws will babysit."),
    ("2026-04-09", "Feeling grateful. The hard part isn't over but I know we can handle it now."),

    # Apr 10-14: Sleep regression hits (5)
    ("2026-04-10", "Baby stopped sleeping through the night again. Sleep regression they call it. Up every 90 minutes."),
    ("2026-04-11", "Two nights of no sleep. I'm snapping at everyone. This feels like February all over again."),
    ("2026-04-12", "Priya and I argued again. Same fight about who's more tired. I thought we were past this."),
    ("2026-04-13", "Missed a deadline at work because I couldn't think straight. Three hours of sleep does that."),
    ("2026-04-14", "I recognize this feeling. The exhaustion, the irritability, the guilt. Last time it spiraled. I need to ask for help before it does."),
]

# =====================================================================
# PROFILE 4: athlete_priya — Injury → frustration → rehab → comeback
# =====================================================================
ATHLETE_ENTRIES = [
    # Jan 15-31: Peak performance, confident (10)
    ("2026-01-15", "Best training session this year. Hit a new personal record on the 400m. Coach says I'm on track for nationals."),
    ("2026-01-17", "Morning run in the cold. 10km in 42 minutes. My body feels like a machine. Everything is clicking."),
    ("2026-01-19", "Won the district meet. Gold medal in 400m and silver in 200m. Team celebrated. Best day."),
    ("2026-01-21", "Recovery day. Yoga, ice bath, good nutrition. Taking care of my body like it's my job. Because it is."),
    ("2026-01-23", "Speed work went perfectly. Coach is talking about Olympic trials timeline. I can see it happening."),
    ("2026-01-25", "Rest day with the team. Movie night and protein shakes. These people understand me like no one else."),
    ("2026-01-27", "Interval training was brutal but I loved every second. The burn means growth."),
    ("2026-01-28", "Sports nutritionist adjusted my diet. More iron, more protein. Feeling the difference already."),
    ("2026-01-30", "Mental conditioning session. Visualization exercises for race day. I can see myself crossing that finish line."),
    ("2026-01-31", "January was incredible. Fastest month of training ever. Everything is aligned."),

    # Feb 1-9: Minor warning signs (5)
    ("2026-02-01", "Slight pain in my right knee during sprints. Coach said to ice it. Probably nothing."),
    ("2026-02-03", "Knee pain is still there. Pushed through training anyway. I can't afford to slow down."),
    ("2026-02-05", "Physiotherapist said I should rest for a week. A WEEK. Nationals are in 3 months. I can't stop."),
    ("2026-02-07", "Trained through the pain. Wrapped the knee tight. It's mind over matter. Athletes push through."),
    ("2026-02-09", "Knee swelled up after practice. Had to limp to the car. Coach saw and was upset I didn't tell him."),

    # Feb 10-20: Injury confirmed, devastation (8)
    ("2026-02-10", "MRI results. Partial ACL tear. Doctor said no running for 8-12 weeks. My world just collapsed."),
    ("2026-02-11", "Cried for hours. Nationals is impossible now. Everything I worked for. All those mornings. All those sacrifices. Gone."),
    ("2026-02-13", "Team had practice today. I watched from the bench. Seeing them run while I sit here with an ice pack. Torture."),
    ("2026-02-14", "Angry at myself. I felt the pain and ignored it. If I had rested when the physio said, maybe this wouldn't have happened."),
    ("2026-02-16", "Can't sleep. Keep replaying that training session where I felt the pop. What if I had stopped?"),
    ("2026-02-17", "Mom says it's not the end of the world. She doesn't understand. Running IS my world."),
    ("2026-02-19", "Saw my teammates post training videos. Had to mute them on social media. It hurts too much to watch."),
    ("2026-02-20", "What am I if I'm not an athlete? I don't know who I am without running. That scares me."),

    # Feb 21-28: Starting rehab, tiny progress (5)
    ("2026-02-21", "First physiotherapy session. Basic exercises. Moving my knee in circles. It's humiliating but it's something."),
    ("2026-02-23", "Got through a full rehab session without wincing. Small victory but I'll take it."),
    ("2026-02-25", "Started swimming for cardio. It's not running but at least I'm moving. Water feels forgiving."),
    ("2026-02-27", "Coach came to visit. Said my spot on the team is safe. Nationals isn't everything — there are other competitions."),
    ("2026-02-28", "End of the worst month of my life. But I'm doing rehab every day. Forward is forward, even if it's slow."),

    # Mar 1-31: Rehab progress, finding identity (12)
    ("2026-03-01", "Walked 2km today without pain. Two months ago that was a warm-up jog. Today it's a milestone."),
    ("2026-03-04", "Light jogging approved! 5 minutes on the treadmill. My knee held. I almost cried — happy tears this time."),
    ("2026-03-07", "Started volunteering as a junior coach. Teaching kids sprinting technique. It fills a different part of me."),
    ("2026-03-09", "Jogged outside for the first time. Slowly. Trees, birds, sunshine. I forgot how beautiful running can be when you're not racing."),
    ("2026-03-12", "Physio says I'm ahead of schedule. The swimming and consistency are paying off."),
    ("2026-03-14", "Had a long talk with a teammate who recovered from the same injury. She said month 4 is when it gets good. I believe her."),
    ("2026-03-17", "Ran 3km without stopping. Slow pace but steady. My knee feels stable. Hope is rebuilding."),
    ("2026-03-20", "Coach included me in team strategy sessions. Even if I can't race, I'm part of the team. That matters."),
    ("2026-03-23", "Tried light sprint drills. Short bursts. It felt like coming home. The track under my feet again."),
    ("2026-03-26", "Ran 5km today. Not fast, not pretty, but complete. My body is remembering."),
    ("2026-03-28", "Junior kids I'm coaching won their school relay. Their joy filled me up. Coaching is healing."),
    ("2026-03-31", "Best month of rehab. I can see the comeback now. It's not 'if' anymore — it's 'when.'"),

    # Apr 1-9: Return to training, cautious optimism (5)
    ("2026-04-01", "Back in group training! Modified drills but I'm ON the track with my team. Alive again."),
    ("2026-04-03", "Speed test today. 80% of my pre-injury pace. Coach says that's excellent for week 8 of rehab."),
    ("2026-04-05", "Registered for a regional meet in May. Not nationals, but a real competition. I have a target now."),
    ("2026-04-07", "Full sprint session. Knee held perfectly. I screamed with joy and the team laughed. Good tears."),
    ("2026-04-09", "Feeling strong. Nervous about the regional meet but excited. This is the right kind of nervous."),

    # Apr 10-14: Comeback anxiety + knee twinges (5)
    ("2026-04-10", "Felt a twinge in the knee during sprints today. Minor but it sent a wave of panic through me. Not again."),
    ("2026-04-11", "Can't stop thinking about the knee. Every step I'm scanning for pain. The fear is worse than the pain."),
    ("2026-04-12", "Physio says the knee is fine — it's normal soreness, not re-injury. But my brain won't believe it."),
    ("2026-04-13", "Teammates are running faster than me now. I'm falling behind. What if I never get back to where I was?"),
    ("2026-04-14", "The anxiety about my knee is exactly like February — lying awake, catastrophizing, losing confidence. I need to talk to someone before the meet."),
]


PROFILES = {
    "student_ananya": STUDENT_ENTRIES,
    "parent_rahul": PARENT_ENTRIES,
    "athlete_priya": ATHLETE_ENTRIES,
}


def seed_profile(user_id: str, entries: list):
    """Seed entries for a single user profile."""
    print(f"\nSeeding {len(entries)} entries for '{user_id}'...")
    for i, (date_str, transcript) in enumerate(entries):
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=random.randint(8, 20),
            minute=random.randint(0, 59),
            tzinfo=timezone.utc,
        )
        vector = generate_embedding(transcript)
        sentiment = analyze_sentiment(transcript)
        keywords = extract_keywords(transcript)
        payload = {
            "user_id": user_id,
            "date": date_str,
            "timestamp": int(dt.timestamp()),
            "transcript": transcript,
            "sentiment_score": sentiment,
            "keywords": keywords,
            "week_number": dt.isocalendar()[1],
            "month": dt.strftime("%Y-%m"),
            "entry_type": "checkin",
        }
        point_id = upsert_entry(vector, payload)
        print(f"  [{i+1:2d}/{len(entries)}] {date_str} | sentiment={sentiment:+.2f} | {point_id[:8]}...")


def seed_all():
    """Seed all profiles."""
    print("Creating collection...")
    create_collection()
    for user_id, entries in PROFILES.items():
        seed_profile(user_id, entries)
    print(f"\nDone! Seeded {sum(len(e) for e in PROFILES.values())} entries across {len(PROFILES)} profiles.")


if __name__ == "__main__":
    seed_all()
