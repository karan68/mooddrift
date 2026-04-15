# MoodDrift — Feature Roadmap

> Priority: P0 = must ship, P1 = high value, P2 = nice to have

---

## P0: Telegram Bot — Async Check-in & Nudges

### Problem
Voice calls are spam-flagged, can't be taken in public, and create pressure to respond immediately. Our target audience (anxious, overwhelmed people) avoids phone calls.

### Solution
Telegram bot that:
1. **Sends daily nudge** at user's preferred time: "Hey, how are you feeling today? Reply with a voice note or text."
2. **Receives voice notes** → transcribes → embeds → stores in Qdrant (same pipeline as Vapi)
3. **Receives text messages** → embeds → stores
4. **Sends voice summaries back** when drift is detected: generates TTS voice note with the insight
5. **Sends weekly recap** as voice note: "This week you mentioned work stress 4 times. Your entries feel more negative than last week."

### Why Telegram (not WhatsApp)
- Free API, no Meta approval needed
- Supports voice messages both directions
- No 24-hour template window restriction
- Bot creation takes 30 seconds via @BotFather
- 50M+ users in India

### Technical Plan
- `python-telegram-bot` library
- Webhook mode (Render receives Telegram updates)
- Voice note → download .ogg → transcribe via Groq Whisper API (free tier)
- Same embedding/sentiment/keywords/drift pipeline as Vapi webhook
- Daily scheduler: APScheduler or Celery beat (lightweight cron)
- TTS for outbound voice notes: Groq or edge-tts (free, offline)

### Endpoints
| Trigger | Action |
|---|---|
| User sends voice note | Transcribe → embed → store → drift check → reply with insight |
| User sends text | Embed → store → drift check → reply |
| Daily cron (user's preferred time) | Send nudge message |
| Weekly cron (Sunday evening) | Generate voice summary → send as voice note |
| Drift detected | Send alert: "I noticed a shift in your recent entries..." |

### Demo Flow
1. Open Telegram, find @MoodDriftBot
2. Send a voice note: "I'm feeling stressed about deadlines"
3. Bot replies: "Stored. Your sentiment is -0.4. I noticed your recent entries feel similar to mid-February when you described burnout."
4. Show the entry appearing on the dashboard in real-time

---

## P0: Coping Strategy Memory

### Problem
MoodDrift says "this feels like February" but doesn't remember what HELPED in February. The user has to scroll through entries to find it.

### Solution
- During recovery entries, the agent asks: "What helped you feel better?"
- Store the response tagged as `entry_type: "coping_strategy"` with the associated drift period
- When new drift is detected, retrieve matching coping strategies: "Last time this happened, you said taking a weekend offline helped. Want to try that?"

### Technical Plan
- New payload field: `coping_strategy: string | null`
- New Qdrant filter: `entry_type == "coping_strategy"`
- Drift engine: when drift detected, also search for coping strategies from the matching historical period
- Vapi system prompt update: add step to ask "what helped?" when user reports feeling better

---

## P1: Dashboard — Reminder Settings & WhatsApp Concept UI

### Problem
Dashboard has no user settings. No way to configure reminders. No indication that MoodDrift will proactively reach out.

### Solution
Add a Settings panel to the dashboard:
1. **Reminder channel**: Telegram (active) / WhatsApp (coming soon)
2. **Reminder time**: Dropdown — morning (8am), afternoon (2pm), evening (8pm)
3. **Weekly summary**: On/Off toggle
4. **Trusted contact**: Phone/email of someone to notify if drift exceeds threshold (opt-in)

### WhatsApp Concept UI
Show a mockup card: "Next check-in reminder: Tomorrow 8:00 PM via WhatsApp" with a note "WhatsApp integration coming soon. Using Telegram for now."

This demonstrates the product vision to judges without requiring Meta Business API approval.

---

## P1: Weekly Voice Summary

### Problem
Users don't open dashboards. Insights need to go TO the user, not wait for them.

### Solution
Every Sunday at the configured time, the Telegram bot sends a voice note:
- "Hi Ananya, here's your weekly reflection. You checked in 5 times this week. Your average mood was slightly lower than last week. You mentioned deadlines 3 times and sleep problems twice. Your entries are showing a mild drift — similar to early February. Last time, talking to your roommate and visiting the campus counselor helped. Take care of yourself."

### Technical Plan
- Weekly cron job triggers for each user
- Pull last 7 days of entries from Qdrant
- Compute drift, extract top keywords, average sentiment
- Generate summary text via Groq LLM
- Convert to speech via edge-tts
- Send as Telegram voice note

---

## P1: Exportable Report for Therapist

### Problem
Users see a therapist every 2 weeks. First 15 minutes is spent catching up. If the therapist had a summary, they could skip to real work.

### Solution
"Export last 2 weeks" button on dashboard that generates a PDF:
- Drift timeline chart
- Sentiment trend
- Top keywords / themes
- Key entries (highest drift, most negative, recovery moments)
- Coping strategies used

### Technical Plan
- Backend endpoint: `GET /api/report?user_id=&days=14`
- Returns structured JSON
- Frontend renders to PDF via browser print / jsPDF
- Simple, clean, one-page format

---

## P2: Trusted Contact Alerts (Opt-in)

### Problem
Someone spiraling may not recognize it or seek help. A trusted person who gets a gentle alert could intervene.

### Solution
- User opts in and adds a trusted contact (phone or Telegram)
- User sets threshold: "Notify if drift score exceeds 0.5 for more than 5 days"
- Alert sent to trusted contact: "Hey, [User] has given you permission to know when they might need support. Their recent journal entries suggest they're going through a tough time. You might want to check in with them."
- **Never shares entry content.** Only the fact that drift was detected.

### Privacy Rules
- Strictly opt-in
- User can revoke anytime
- No transcript/entry content shared — only drift status
- Trusted contact can't access dashboard or entries

---

## P2: Consistency Acknowledgment

### Problem
No positive reinforcement for maintaining the journaling habit.

### Solution
- Track check-in streak per user
- After 7, 14, 30 days: Telegram message acknowledging consistency
- "You've reflected 14 days in a row. People who journal consistently report better emotional clarity. Keep going."
- No gamification language (no "streak broken!" guilt)

---

## Implementation Order

| Sprint | Feature | Effort |
|---|---|---|
| **Now** | Telegram bot (nudge + voice note receive + reply) | 3-4 hours |
| **Now** | Dashboard reminder settings + WhatsApp concept UI | 1-2 hours |
| **Next** | Coping strategy memory (tag + recall) | 2-3 hours |
| **Next** | Weekly voice summary via Telegram | 2 hours |
| **Later** | Exportable therapist report | 2 hours |
| **Later** | Trusted contact alerts | 3 hours |
| **Later** | Consistency acknowledgment | 1 hour |
