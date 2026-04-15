# MoodDrift — Voice Mood Tracker with Semantic Drift Detection

> *"Your journal that listens, remembers, and notices what you don't."*

**Track:** PS3 — Voice AI Agent for Accessibility & Societal Impact  
**Stack:** Qdrant + Vapi + FastAPI + React

---

## What is MoodDrift?

MoodDrift is a voice-first emotional self-awareness tool. Users do a 2-minute daily voice check-in via Vapi. The system embeds their words as vectors, stores them in Qdrant with temporal metadata, and detects **semantic drift** — gradual emotional shifts the user wouldn't notice themselves.

When drift is detected, the agent surfaces historical patterns mid-conversation:  
*"Your entries this week feel similar to mid-February when you described burnout. Back then, you said taking a weekend off helped."*

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Qdrant Cloud account (free tier)
- Vapi account
- Groq API key (free tier)

### 1. Backend Setup

```bash
cd backend

# Create .env from template
cp ../.env.example .env
# Edit .env with your real keys (QDRANT_URL, QDRANT_API_KEY, GROQ_API_KEY, VAPI_API_KEY)

# Install dependencies
pip install -r requirements.txt

# Seed demo data (60 entries with narrative arc)
python -m seed.seed_data

# Start the server
uvicorn main:app --port 8000 --reload
```

### 2. Dashboard Setup

```bash
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173 — dashboard auto-refreshes every 5 seconds.

### 3. Vapi Assistant Setup

```bash
cd backend

# Expose backend publicly (for Vapi webhooks)
ngrok http 8000

# Create the assistant in Vapi
python scripts/create_assistant.py --server-url https://YOUR_NGROK_URL
```

Add the returned `VAPI_ASSISTANT_ID` to your `.env`.

---

## Architecture

```
User → Vapi (voice) → FastAPI Backend → Qdrant (vectors + metadata)
                                ↓
                    Drift Engine (centroid comparison)
                                ↓
                    Dashboard (React + Recharts)
```

| Layer | Technology |
|---|---|
| Voice Agent | Vapi (multi-turn, function calling, Hindi support) |
| Backend | Python + FastAPI |
| Vector DB | Qdrant Cloud (free tier) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384-dim, local) |
| Sentiment | VADER (nltk) |
| Dashboard | React + Vite + TypeScript + Recharts |
| Dimensionality Reduction | UMAP |

---

## API Endpoints

### Vapi Webhook
| Method | Path | Purpose |
|---|---|---|
| POST | `/vapi/webhook` | Handles tool-calls, function-calls, end-of-call-report |

### Dashboard
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/entries?days=90` | Get entries for a user |
| GET | `/api/drift-timeline?days=90` | Weekly drift scores |
| GET | `/api/drift-current` | Current drift status |
| GET | `/api/visualization?days=90` | UMAP 2D coordinates |

### Admin (demo)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/entries` | Manually create an entry |
| POST | `/api/seed` | Seed 60 demo entries |
| DELETE | `/api/entries` | Clear all entries for a user |

---

## Drift Detection Algorithm

1. **Recent Window**: entries from last 7 days → compute centroid
2. **Baseline Window**: entries from 8–30 days ago → compute centroid
3. **Drift Score**: `1 - cosine_similarity(recent, baseline)`
4. **Threshold**: score > 0.25 → drift detected
5. **Pattern Matching**: search Qdrant for historical entries similar to recent centroid
6. **Severity**: 0.25–0.40 mild, 0.40–0.60 moderate, 0.60+ significant

---

## Project Structure

```
├── backend/
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Environment config
│   ├── routers/
│   │   ├── vapi_webhook.py        # Vapi webhook handler
│   │   ├── entries.py             # Manual entry creation
│   │   └── dashboard.py           # Dashboard APIs
│   ├── services/
│   │   ├── embedding.py           # sentence-transformers
│   │   ├── qdrant_service.py      # Qdrant client
│   │   ├── drift_engine.py        # Drift detection
│   │   ├── sentiment.py           # VADER
│   │   └── keywords.py            # Keyword extraction
│   ├── models/schemas.py          # Pydantic models
│   ├── seed/seed_data.py          # Demo data seeder
│   └── tests/                     # 100 tests
├── dashboard/
│   ├── src/
│   │   ├── App.tsx                # Main layout + disclaimer
│   │   ├── components/
│   │   │   ├── ScatterPlot.tsx    # UMAP embedding visualization
│   │   │   ├── DriftTimeline.tsx  # Drift score line chart
│   │   │   └── EntryList.tsx      # Entry list + drift badge
│   │   ├── hooks/useEntries.ts    # Data fetching (5s polling)
│   │   └── utils/api.ts           # API client
│   └── ...
├── vapi/
│   └── assistant_config.json      # Vapi assistant configuration
└── PROJECT.md                     # Full project specification
```

---

## Testing

```bash
cd backend

# Run all tests (100 tests)
python -m pytest tests/ -v

# Unit tests only (no external services needed)
python -m pytest tests/ -m unit

# Integration tests only (requires Qdrant)
python -m pytest tests/ -m integration
```

---

## Demo Flow

1. **Pre-seed** 60 entries (Jan–Apr narrative arc)
2. **Live voice check-in** via Vapi — triggers drift detection in real-time
3. **Dashboard** shows the new entry appear, scatter plot clusters, drift timeline spike

---

## Disclaimers

- MoodDrift is an emotional self-awareness and journaling tool. It is **NOT** a medical device, diagnostic tool, or substitute for professional mental health care.
- If you or someone you know is in crisis, contact iCall at 9152987821 or Vandrevala Foundation at 1860-2662-345.
- Insights are based on pattern recognition in your own words. They may be inaccurate or incomplete.
