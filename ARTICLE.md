# How We Built a Journal That Talks Back — MoodDrift at BL-Hack 2026

*A voice-first emotional awareness tool that listens to your words, remembers what helped, and notices the patterns you can't see yourself.*

---

## The Problem Nobody Talks About

Here's a number that should bother you: **85%**.

That's the dropout rate for journaling apps within two weeks. Eighty-five percent. The very tool that therapists, researchers, and wellness gurus swear by — "just write down how you feel!" — fails almost everyone who tries it.

We asked ourselves: *why?*

The answers were painfully obvious once we stopped to listen:

- **Typing is friction.** When you're overwhelmed, the last thing you want to do is stare at a blank text box and compose your feelings into sentences.
- **Nobody reads their own patterns.** You don't notice you're drifting into burnout until you're already burned out. The journal has the data — but no one's analyzing it.
- **Accessibility is an afterthought.** People with low literacy, motor disabilities, or simply those who think better out loud? Excluded entirely.

We wanted to build something different. Not another app that asks you to rate your day with a smiley face. Something that actually *listens*.

---

## The Idea: What If Your Journal Could Talk?

MoodDrift is built on a simple but powerful premise:

> **Your words carry more meaning than any emoji slider.**

When you say "I can barely sleep, deadlines are crushing me, and I snapped at my colleague today" — that sentence contains a rich semantic fingerprint. It's not a 3/5. It's not a 😐. It's a vector in 384-dimensional space that can be compared, clustered, and tracked over time.

What if we could:
1. Let you **speak** instead of type — 2 minutes via voice note on Telegram
2. **Embed** your words as vectors and store them with timestamps
3. **Compare** this week's emotional centroid against your baseline
4. **Detect** when you're drifting — before you notice it yourself
5. **Remember** what helped last time and surface it exactly when you need it

That's MoodDrift.

---

## The Architecture (aka "How does talking into Telegram become insight?")

```mermaid
graph TB
    subgraph "User Touchpoints"
        TG["📱 Telegram Bot"]
        VAPI["🎤 Vapi Voice Agent"]
        DASH["💻 Web Dashboard"]
    end

    subgraph "Backend (FastAPI on Render)"
        WH["Webhook Handler"]
        EMB["Embedding Service<br/>all-MiniLM-L6-v2"]
        SENT["Sentiment Analyzer<br/>VADER + Context Corrections"]
        KW["Keyword Extractor"]
        DRIFT["Drift Detection Engine"]
        TTS["Text-to-Speech<br/>edge-tts"]
        LLM["Summary Generator<br/>Groq Llama 3.3"]
        WHISPER["Transcription<br/>Groq Whisper"]
    end

    subgraph "Data Layer"
        QD[("Qdrant Cloud<br/>Vector DB")]
    end

    TG -->|voice note| WHISPER
    TG -->|text| WH
    VAPI -->|function call| WH
    WHISPER --> WH
    WH --> EMB --> QD
    WH --> SENT
    WH --> KW
    WH --> DRIFT
    DRIFT -->|scroll + search| QD
    DRIFT -->|coping recall| QD
    LLM -->|weekly recap| TTS
    TTS -->|voice note| TG
    QD --> DASH

    style QD fill:#E74C3C,color:#fff
    style DRIFT fill:#F39C12,color:#fff
    style TG fill:#0088cc,color:#fff
    style VAPI fill:#6C5CE7,color:#fff
```

The secret sauce isn't any single component — it's how they compose. Qdrant isn't just storing vectors; it's being used as a **temporal vector analysis engine**. We're not doing RAG. We're doing something the Qdrant team probably didn't expect: comparing vector distributions over time to detect emotional shift.

---

## The Drift Detection Algorithm

This is the heart of MoodDrift. Here's how it works:

```mermaid
flowchart LR
    A["Last 7 days<br/>of entries"] --> B["Compute<br/>centroid"]
    C["8-30 days ago<br/>entries"] --> D["Compute<br/>centroid"]
    B --> E{"Cosine<br/>similarity"}
    D --> E
    E -->|"> 0.75"| F["✅ Stable"]
    E -->|"< 0.75"| G["⚠️ Drift<br/>Detected"]
    G --> H["Search Qdrant<br/>for similar<br/>historical period"]
    H --> I["Find coping<br/>strategies from<br/>that period"]
    I --> J["Surface to user:<br/>'Last time this happened,<br/>taking a weekend off helped'"]
```

The algorithm computes the **centroid** (mean vector) of your recent entries and compares it to your baseline. If the cosine similarity drops below 0.75, drift is detected. Then it searches for which historical period matches your current state — and retrieves what *you said helped* last time.

This isn't generic advice. It's *your own words*, from *your own recovery*, served back to you at exactly the moment you need them.

---

## The Five Personas: Making Data Feel Human

A demo with one user profile is a tech demo. Five personas with complete emotional arcs? That's a product.

We created five realistic journaling profiles, each with 45-62 entries spanning 3 months:

```mermaid
graph LR
    subgraph "Karan 👨‍💻"
        K1["Jan: Stable"] --> K2["Feb: Burnout"] --> K3["Mar: Recovery"] --> K4["Apr: New drift"]
    end
    
    subgraph "Ananya 👩‍🎓"
        A1["Jan: Confident"] --> A2["Feb: Exam panic"] --> A3["Mar: Counseling"] --> A4["Apr: Finals fear"]
    end
    
    subgraph "Rahul 👶"
        R1["Jan: New dad joy"] --> R2["Feb: Exhaustion"] --> R3["Mar: Rhythm"] --> R4["Apr: Regression"]
    end
    
    subgraph "Priya 🏃‍♀️"
        P1["Jan: Peak"] --> P2["Feb: ACL tear"] --> P3["Mar: Rehab"] --> P4["Apr: Comeback anxiety"]
    end
    
    subgraph "Meera 👩‍🏫 ✦"
        M1["Jan: Burnt out"] --> M2["Feb: Sabbatical"] --> M3["Mar: Boundaries"] --> M4["Apr: THRIVING"]
    end
```

Meera is the star. She's the teacher who burns out in January, takes a sabbatical, travels to Rishikesh, rediscovers yoga and painting, returns with boundaries, and ends up **thriving**. She exists to prove that MoodDrift doesn't just detect problems — it celebrates recovery.

---

## The Telegram Bot: Where Users Actually Live

We built a beautiful web dashboard. Then we realized nobody would open it.

> The insight has to go TO the user. Not sit on a webpage waiting.

Enter **@MoodDriftBot** on Telegram. Here's the daily flow:

```mermaid
sequenceDiagram
    participant Cron as ⏰ Cron Job
    participant Bot as 🤖 MoodDrift Bot
    participant User as 👤 User
    participant BE as ⚙️ Backend
    participant QD as 🔴 Qdrant

    Cron->>Bot: 8 PM nudge
    Bot->>User: "How are you feeling today? 🎤"
    User->>Bot: 🎤 Voice note (30 sec)
    Bot->>BE: Download + Whisper transcribe
    BE->>BE: Embed + Sentiment + Keywords
    BE->>QD: Store vector + payload
    BE->>BE: Drift detection
    BE->>BE: Coping strategy recall
    
    alt Drift detected
        BE->>BE: Generate TTS voice note
        Bot->>User: "⚠️ I noticed a shift..."
        Bot->>User: 🔊 Voice note with insight
    else Stable
        Bot->>User: "😊 Entry stored. Themes: work, sleep"
    end

    Note over Cron,User: Sunday 8 PM
    Cron->>Bot: Weekly recap trigger
    BE->>BE: Groq LLM summary
    BE->>BE: edge-tts voice note
    Bot->>User: 📅 "Here's your weekly reflection..."
    Bot->>User: 🔊 Personalized voice summary
```

Why Telegram and not WhatsApp? Free API, no Meta approval, voice notes both ways, no 24-hour template window. 50M+ users in India. The decision took 30 seconds.

---

## The Sentiment Problem (and How We Fixed It)

We started with VADER from NLTK. It's the standard. It's fast. It's free.

It's also **terribly wrong** for mental health language.

| Entry | VADER Score | Reality |
|---|---|---|
| "Two nights of no sleep. I'm snapping at everyone." | **+0.08** 😐 | Obviously negative |
| "Deadlines everywhere, skipping meals, barely sleeping" | **+0.18** 🙂 | Very negative |
| "Mind won't stop racing about deadlines" | **+0.22** 🙂 | Negative |

VADER is lexicon-based. It scores individual words. "Sleep" isn't negative. "Everyone" isn't negative. "No sleep" together is devastating — but VADER doesn't understand two-word context.

**Our fix:** Keep VADER as the base (it handles 70% of cases well), then add 20+ regex-based corrections for patterns VADER systematically misses:

```python
_NEGATIVE_PATTERNS = [
    r"\bno sleep\b", r"\bcan'?t sleep\b", r"\bbarely slept?\b",
    r"\bsnapp(?:ing|ed)\b", r"\bskipp(?:ing|ed) meals?\b",
    r"\bpanic attack\b", r"\bcried\b", r"\bbroke(?:n)? down\b",
    r"\ball over again\b",  # "this feels like X all over again"
    ...
]
```

**After the fix:**

| Entry | Before | After | Correct? |
|---|---|---|---|
| "No sleep, snapping at everyone" | +0.08 | **-0.67** | ✅ |
| "Skipping meals, barely sleeping" | +0.18 | **-0.07** | ✅ |
| "Gym felt amazing, sleeping well" | +0.82 | **+0.86** | ✅ |

VADER + domain-specific context corrections. Still VADER at the core — just smarter about mental health language.

---

## The Feature That Could Save Someone

We almost didn't build this one. Trusted Contact Alerts.

The idea: if your emotional drift score stays dangerously high for several days, and you've opted in, MoodDrift sends a gentle message to someone you trust.

Not your therapist. Not a helpline. Your mom. Your best friend. Your partner.

> "Hi — Karan has given you permission to receive this message. Their recent journal entries suggest they may be going through a difficult time. You might want to check in with them. No entry content is shared — only that a pattern was noticed. — MoodDrift"

The privacy rules are strict:
- **Opt-in only.** You set `/trust @username` in Telegram.
- **Revocable anytime.** `/untrust` removes it instantly.
- **No content shared.** Ever. Only the fact that drift was detected.
- **Trusted contact can't access anything.** No dashboard, no entries, nothing.

This feature exists because sometimes the person spiraling is the last one to notice.

---

## What We Actually Built: The Numbers

| Metric | Count |
|---|---|
| Backend endpoints | 15 |
| Test cases | **157** (all passing) |
| Seeded journal entries | 261 across 5 profiles |
| User personas | 5 (4 drift arcs + 1 positive) |
| Telegram bot commands | 6 (/start, /status, /recap, /trust, /untrust, voice/text) |
| Cron jobs | 5 |
| Services integrated | Qdrant, Vapi, Groq (LLM + Whisper), edge-tts, Telegram, Render |
| Lines of Python | ~2,500 |
| Lines of TypeScript | ~1,200 |
| Dashboard tabs | 4 (Today, Journal, Insights, Settings) |

---

## The Tech Stack (and Why)

| Choice | Why |
|---|---|
| **Qdrant** (mandatory) | Not just vector search — temporal vector distribution analysis. Scroll API with payload filtering = time-series for emotions. |
| **Vapi** (mandatory) | Multi-turn voice conversations with function calling. The agent calls Qdrant mid-conversation to reference past entries by date. |
| **Groq** (Llama 3.3 70B) | Free, fast, generates warm natural-language summaries. Not clinical. Not robotic. |
| **sentence-transformers** (MiniLM) | Local, free, 384-dim. No API call needed for embeddings. Runs on Render free tier. |
| **edge-tts** | Free Microsoft Neural voices. Indian English. Converts weekly recaps to voice notes. |
| **Telegram Bot API** | Free, instant, voice notes both ways, no approval needed. The user is already there. |
| **React + Vite** | Fast, warm UI. Tab navigation. Print-to-PDF therapist reports. |

---

## The Differentiator (Memorize This)

If anyone asks "How is this different from Daylio?"

> "Daylio can tell you 'you rated Tuesday a 3/5.' MoodDrift can tell you 'your entries this week sound like mid-February, when you were burning out from deadline pressure — and back then, you said taking a weekend offline helped. Would that work for you right now?'"
>
> **They track. We understand.**

---

## What's Next

MoodDrift today is an MVP. Here's what makes it a product:

1. **WhatsApp integration** — when Meta Business API approval comes through, the 500M daily users in India get access.
2. **Persistent user storage** — replace in-memory registry with a real database.
3. **Therapist portal** — therapists receive reports directly, not via PDF.
4. **Multi-language embeddings** — full Hindi, Tamil, Bengali support with multilingual sentence transformers.
5. **Wearable correlation** — sleep data from smartwatches correlated with journal sentiment (but carefully — we're a mirror, not a doctor).

---

## The Team

Built in 48 hours at BL-Hack 2026, Bangalore.

Not because we had to. Because 450 million people with mental health conditions deserve a journal that actually works for them.

*MoodDrift doesn't diagnose. It mirrors. It's your journal that listens, remembers, and notices what you don't.*

---

**GitHub:** [github.com/karan68/mooddrift](https://github.com/karan68/mooddrift)  
**Live API:** [mooddrift-api.onrender.com](https://mooddrift-api.onrender.com)  
**Telegram:** [@MoodDriftBot](https://t.me/MoodDriftBot)
