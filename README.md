# MoodDrift — Voice Mood Tracker with Semantic Drift Detection

> *"Your journal that listens, remembers, and notices what you don't."*

**Track:** PS3 — Voice AI Agent for Accessibility & Societal Impact  
**Mandatory Stack:** Qdrant + Vapi  
**Live deployment:** https://mooddrift-api.onrender.com  
**Telegram Bot:** [@MoodDriftBot](https://t.me/MoodDriftBot)

---

## What is MoodDrift?

MoodDrift is a voice-first emotional self-awareness tool. Users journal through **voice notes on Telegram**, **voice calls via Vapi**, or **text**. The system embeds their words as semantic vectors, stores them in Qdrant with temporal metadata, and detects **emotional drift** — gradual shifts the user wouldn't notice themselves.

When drift is detected, MoodDrift surfaces historical patterns AND recalls what helped last time:

> *"Your recent entries feel similar to how you were in February. Last time, you found something that helped: 'Telling my manager I was struggling was the turning point.' — would any of that work for you right now?"*

### What makes it different from Daylio/Reflectly?

| Feature | Mood Tracker Apps | MoodDrift |
|---|---|---|
| Input | Tap emoji / slider | **Voice** (zero friction) |
| What's stored | Number (1-5) | **Full semantic embedding** |
| Pattern detection | "Low 3 days in a row" | **"This week feels like your burnout in February"** |
| Context recall | None | **Retrieves what helped last time** |
| Accessibility | Requires literacy + fine motor | **Works for anyone who can speak** |
| Proactive | Push notification | **Voice note on Telegram with weekly summary** |

---

## Features

### Core (P0)
- **Voice check-in via Vapi** — multi-turn conversation, Hindi greeting, function calling
- **Telegram bot** — voice note + text journaling, daily nudges, drift alerts as voice notes
- **Semantic drift detection** — centroid comparison of recent vs baseline emotional vectors
- **Coping strategy memory** — stores what helped, recalls it during drift
- **VADER + context-aware sentiment** — 20+ regex corrections for mental health language

### Dashboard (P1)
- **Tab navigation** — Today / Journal / Insights / Settings
- **Insight card** — collapsible drift insight with actionable message
- **ScatterPlot** — UMAP 2D visualization of emotional clusters
- **DriftTimeline** — weekly drift score chart with threshold line
- **EntryList** — scrollable entries with sentiment bars + keyword tags
- **Profile selector** — 5 demo profiles with rich tooltips
- **Therapist report** — printable PDF with sentiment trend, key entries, coping strategies
- **Settings** — reminder channel, time, weekly summary, trusted contact, WhatsApp concept UI

### Telegram Bot (P1)
- **Daily nudge** via cron (cron-job.org)
- **Voice note receiving** → Groq Whisper transcription → full pipeline
- **TTS voice replies** on drift detection (edge-tts, Indian English voice)
- **Weekly voice recap** — Groq LLM generates summary, edge-tts converts to voice note
- **Coping flow** — asks "what helped?" when sentiment improves, stores as strategy
- **Trusted contact alerts** — opt-in, sends gentle alert if sustained high drift
- **Consistency acknowledgment** — milestones at 7, 14, 30 days

---

## Architecture

```
User → Telegram Bot / Vapi Voice / Dashboard
            ↓
     FastAPI Backend (Render)
            ↓
   ┌────────┼────────┐
   ↓        ↓        ↓
Embedding  Sentiment  Keywords
(MiniLM)   (VADER+)   (nltk)
   ↓        ↓        ↓
   └────────┼────────┘
            ↓
      Qdrant Cloud
      (vectors + metadata)
            ↓
      Drift Engine
      (centroid comparison)
            ↓
   ┌────────┼────────┐
   ↓        ↓        ↓
 Insight   Coping    TTS
 Message   Recall    (edge-tts)
```

| Layer | Technology |
|---|---|
| Voice Agent | Vapi (Groq LLM, function calling, Hindi) |
| Messaging | Telegram Bot API (webhook mode) |
| Backend | Python + FastAPI |
| Vector DB | Qdrant Cloud (free tier) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384-dim, local, CPU) |
| Sentiment | VADER + 20 context-aware regex corrections |
| LLM Summaries | Groq (Llama 3.3 70B) |
| TTS | edge-tts (Microsoft Neural voices, Indian English) |
| Transcription | Groq Whisper |
| Dashboard | React + Vite + TypeScript + Recharts |
| Visualization | UMAP |
| Deployment | Render (free tier) |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Qdrant Cloud account (free tier)
- Groq API key (free tier)
- Vapi account
- Telegram @BotFather token

### 1. Backend

```bash
cd backend
cp ../.env.example .env
# Fill in: QDRANT_URL, QDRANT_API_KEY, GROQ_API_KEY, VAPI_API_KEY, TELEGRAM_BOT_TOKEN

pip install -r requirements.txt
python -m seed.seed_data         # Seed 62 entries (demo_user)
python -m seed.seed_profiles     # Seed 4 more profiles (196 entries)
uvicorn main:app --port 8000
```

### 2. Dashboard

```bash
cd dashboard
echo "VITE_VAPI_ASSISTANT_ID=your-id" > .env
npm install
npm run dev
```

Open http://localhost:5173

### 3. Vapi Assistant

```bash
cd backend
python scripts/create_assistant.py --server-url https://your-render-url
```

### 4. Telegram Bot

```bash
cd backend
python scripts/setup_telegram.py --url https://your-render-url
```

Then open Telegram → @MoodDriftBot → /start

### 5. Cron Jobs (cron-job.org)

| Job | Schedule | URL | Method |
|---|---|---|---|
| Keep warm | `*/10 * * * *` | `GET https://your-render-url/health` | GET |
| Daily nudge | `30 14 * * *` (8 PM IST) | `POST .../telegram/nudge` | POST |
| Weekly recap | `30 14 * * 0` (Sun 8 PM IST) | `POST .../telegram/weekly-recap` | POST |
| Trusted alerts | `0 15 * * *` (8:30 PM IST) | `POST .../telegram/check-trusted-alerts` | POST |
| Consistency | `0 15 * * *` (8:30 PM IST) | `POST .../telegram/check-consistency` | POST |

---

## API Endpoints

### Vapi
| Method | Path | Purpose |
|---|---|---|
| POST | `/vapi/webhook` | Vapi tool-calls, function-calls, end-of-call |

### Dashboard
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/entries?user_id=&days=90` | Get entries |
| GET | `/api/drift-timeline?days=90` | Weekly drift scores |
| GET | `/api/drift-current` | Current drift status |
| GET | `/api/visualization?days=90` | UMAP 2D coordinates |
| GET | `/api/report?days=14` | Therapist report |

### Telegram
| Method | Path | Purpose |
|---|---|---|
| POST | `/telegram/webhook` | Telegram message handler |
| POST | `/telegram/nudge` | Daily nudge (cron) |
| POST | `/telegram/weekly-recap` | Weekly voice recap (cron) |
| POST | `/telegram/check-trusted-alerts` | Trusted contact check (cron) |
| POST | `/telegram/check-consistency` | Milestone check (cron) |

### Admin
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/entries` | Manual entry creation |
| POST | `/api/seed` | Seed demo data |
| DELETE | `/api/entries` | Clear entries |

---

## Demo Profiles

| Profile | User ID | Arc | Entries |
|---|---|---|---|
| **Karan** (Professional) | `demo_user` | Work burnout → recovery → new drift | 62 |
| **Ananya** (Student) | `student_ananya` | Exam anxiety → isolation → balance | 50 |
| **Rahul** (New Parent) | `parent_rahul` | Sleep deprivation → relationship strain → rhythm | 51 |
| **Priya** (Athlete) | `athlete_priya` | Injury → rehab → comeback anxiety | 50 |
| **Meera** (Teacher) ✦ | `teacher_meera` | Burnout → sabbatical → **thriving** (positive arc) | 48 |

Hover over profile pills in the dashboard for detailed story tooltips.

---

## Drift Detection Algorithm

1. **Recent window**: entries from last 7 days → compute vector centroid
2. **Baseline window**: entries from 8-30 days ago → compute centroid
3. **Drift score**: `1 - cosine_similarity(recent, baseline)`
4. **Threshold**: score > 0.25 → drift detected
5. **Pattern matching**: search Qdrant for historical entries similar to recent centroid
6. **Coping recall**: search for `entry_type="coping_strategy"` entries from matching period
7. **Severity**: 0.25-0.40 mild, 0.40-0.60 moderate, 0.60+ significant

---

## Testing

```bash
cd backend
python -m pytest tests/ -v          # All 157 tests
python -m pytest tests/ -m unit     # Unit tests only (no external services)
python -m pytest tests/ -m integration  # Requires Qdrant
```

### Test Coverage

| Area | Tests |
|---|---|
| Config | 2 |
| Coping Strategy | 14 |
| Dashboard API | 13 |
| Drift (integration) | 9 |
| Drift (unit) | 17 |
| Embedding | 6 |
| Features (report, LLM, TTS, trust, consistency) | 23 |
| Keywords | 8 |
| Pipeline | 3 |
| Qdrant | 12 |
| Schemas | 8 |
| Sentiment | 6 |
| Telegram Bot | 20 |
| Vapi Webhook | 16 |
| **Total** | **157** |

---

## Disclaimers

- MoodDrift is an emotional self-awareness and journaling tool. It is **NOT** a medical device, diagnostic tool, or substitute for professional mental health care.
- If you or someone you know is in crisis, contact iCall at 9152987821 or Vandrevala Foundation at 1860-2662-345.
- Insights are based on pattern recognition in your own words. They may be inaccurate or incomplete.
- Trusted contact alerts never share entry content — only that drift was detected.
