# MoodDrift — X-Factor Features

> These 5 features transform MoodDrift from a solid journaling MVP into a hackathon winner. Each one passes a brutal filter: technically impressive, genuinely novel (no competitor does this), deeply tied to Voice AI + Qdrant, and demoable in 60 seconds.

---

## Already Shipped (Foundation)

Before the new features — here's what's live and working:

| Feature | Status |
|---|---|
| Telegram bot (voice + text journaling, daily nudge, weekly voice recap) | ✅ Shipped |
| Vapi voice agent with mid-call function calling | ✅ Shipped |
| Drift detection via temporal vector analysis (centroid comparison) | ✅ Shipped |
| Coping strategy recall ("what helped last time") | ✅ Shipped |
| VADER + 20 mental-health regex corrections | ✅ Shipped |
| Qdrant vector storage with temporal scroll | ✅ Shipped |
| 5 seeded personas (261 entries, complete emotional arcs) | ✅ Shipped |
| Dashboard: entries, scatter plot, drift timeline, therapist report | ✅ Shipped |
| Settings UI (Telegram connect, reminder time, trusted contact) | ✅ Shipped |
| edge-tts voice notes (Indian English) | ✅ Shipped |
| 157 passing tests | ✅ Shipped |

---

## Feature 1: Emotional Voice Biomarkers

### The Insight
When someone says "I'm fine" in a flat, slow monotone — they are not fine. Every mental health professional knows this. Every journaling app ignores it. Text sentiment catches the words. Voice biomarkers catch the truth.

### What It Does
Analyze the **acoustic properties** of every voice note — not just the transcript. Extract:

| Biomarker | What It Reveals | How It's Extracted |
|---|---|---|
| **Pitch variance** (F0 std dev) | Low variance = flat affect = depression signal | `librosa.pyin()` |
| **Speech rate** (syllables/sec) | Rapid = anxiety, slow = fatigue/depression | Word count ÷ audio duration |
| **Pause ratio** | More pauses = cognitive load, hesitation | Energy-based silence detection |
| **Energy (RMS)** | Low energy = withdrawal, high = agitation | `librosa.feature.rms()` |
| **Jitter** | Voice tremor = stress, emotional distress | Pitch period variation |

### The X-Factor: Incongruence Detection
When text sentiment is positive but vocal biomarkers indicate distress → **flag the mismatch**:

> "Your words say things are going well, but your voice sounds different from your baseline. Just checking in — sometimes we say we're fine before we realize we're not."

No app does this. Not Daylio. Not Reflectly. Not Woebot. This is **novel**.

### Technical Plan
```
Voice Note (OGG) → Groq Whisper (transcript) 
                  → librosa (audio features)
                  → Both stored as Qdrant payload

Qdrant payload additions:
  pitch_mean: float
  pitch_std: float  
  speech_rate: float
  pause_ratio: float
  energy_mean: float
  vocal_stress_score: float  (composite 0-1)
  text_voice_congruence: float  (how aligned text + voice are)
```

**New service**: `backend/services/voice_biomarkers.py`
- Uses `librosa` (pure Python, no system deps, runs on Render free tier)
- Extracts features from raw audio bytes before Whisper transcription
- Computes composite `vocal_stress_score` (normalized 0-1)
- Compares against user's historical baseline (Qdrant scroll → compute personal average)

**Dashboard**: New "Voice vs Text" panel in Insights tab
- Dual-axis chart: text sentiment line vs vocal stress line over time
- Divergences highlighted (circles where lines cross/separate)
- Hover shows: "Feb 12: Text says +0.6, Voice says stressed (0.7)"

**Vapi integration**: Agent can reference vocal patterns:
> "I noticed your voice has been lower energy this week compared to January. That sometimes happens before people realize they're dipping. How are you really feeling?"

### Why Judges Will Love This
- Directly advances the "Voice AI" theme — we're not just using voice for input, we're **analyzing the voice itself**
- Clinically grounded — vocal biomarkers are a real research area (published in Nature Digital Medicine, 2023)
- Shows technical depth beyond basic STT
- The incongruence detection is a "holy shit" moment in a demo

### Demo Script (45 seconds)
1. Send a voice note saying "I'm fine, everything's great" in a tired, flat voice
2. Bot replies: "Entry stored. But I want to check — your voice sounds lower energy than usual. Are you really doing okay?"
3. Switch to dashboard → show the Voice vs Text divergence chart
4. Point to where lines separate: "Text says positive. Voice says something different."

---

## Feature 2: Voice Time Capsule

### The Insight
The most powerful coping strategy isn't advice from an app. It's **hearing your own voice from when you were okay.**

Narrative therapy uses this concept — letters to future self, anchoring to positive states. But no app has ever made it voice-first, automatic, and triggered by drift detection.

### What It Does
1. **During good periods** (sentiment > 0.3 sustained for 5+ days), prompt the user:
   > "You've been doing really well lately. Want to record a quick message to your future self? Something you'd want to hear on a tough day."

2. **Store the capsule** in Qdrant with `entry_type: "time_capsule"`, the raw audio bytes, and the transcript.

3. **When drift is detected**, search for time capsules from the matching positive period and **play them back**:
   > "I found a message you recorded on March 15th, when you were feeling strong. Want to hear it?"
   > 🔊 *[User's own voice]: "Hey future me — if you're hearing this, it means things got hard again. But remember, you got through February. You always get through it. Go for a walk. Call Mom. You'll be okay."*

### Why This Is Different From Coping Recall
Coping recall tells you **what helped** (text). Time capsule lets you **hear yourself** (voice). The emotional impact is completely different. Reading "taking a weekend off helped" vs hearing your own confident voice saying "you'll be okay" — there's no comparison.

### Technical Plan
```
Trigger: sentiment > 0.3 for 5 consecutive entries
  → Telegram: "Want to record a message to future you?"
  → Vapi: Agent asks during check-in

Storage (Qdrant):
  entry_type: "time_capsule"
  audio_url: str  (stored in /tmp or S3-compatible)
  transcript: str
  sentiment_at_recording: float
  capsule_prompt: str  ("What would you tell yourself on a bad day?")

Retrieval (on drift detection):
  → Search Qdrant: entry_type="time_capsule", 
    filter by date range matching the positive period
  → Send audio via Telegram voice note
  → Vapi agent plays transcript with context
```

**Telegram flow**:
- Bot: "You've had 5 great days. Want to record a time capsule for future you? 🎤"
- User: sends voice note
- Bot: "Saved. I'll play this back if you ever need to hear it. 💛"
- [Weeks later, drift detected]
- Bot: "Things feel different this week. But you left yourself a message on March 15th. Here it is:"
- Bot: 🔊 [plays back the capsule voice note]

**Dashboard**: "My Time Capsules" section in Settings/Journal tab
- List of capsules with date, transcript preview, play button
- Record new capsule button (uses browser MediaRecorder API)

### Why Judges Will Love This
- Emotionally devastating demo moment — judges will feel it
- Zero competition does this. Literally no journaling app has voice time capsules.
- Shows voice as more than input — it's **therapeutic output**
- Simple to implement (it's a tagged Qdrant entry + audio storage)
- Perfectly answers "why voice and not text?"

### Demo Script (60 seconds)
1. Show Meera's profile (the positive arc)
2. Show her time capsule from March (during sabbatical, thriving)
3. Fast-forward to a hypothetical drift
4. Play the capsule: Meera's own words about finding peace in Rishikesh
5. "This is what she told herself when she was doing well — played back exactly when she needs it."

---

## Feature 3: Trigger Pattern Detection

### The Insight
Drift detection tells you **that** you shifted. Trigger detection tells you **why**.

You don't notice that every Sunday night you spiral. You don't notice that entries mentioning "mom" are 60% more negative. You don't notice that 3pm is consistently your worst time. But your data does — if anyone's looking.

### What It Does
Automatically correlate **entities, times, and recurring themes** with sentiment to identify consistent emotional triggers:

> "📊 Pattern detected: Your entries mentioning **Monday meetings** have an average sentiment of -0.4, compared to your overall average of +0.1. This has been consistent across 8 entries over 6 weeks."

> "📊 Pattern detected: Your entries recorded **after 10 PM** are 35% more negative than daytime entries. Late-night journaling correlates with lower mood for you."

> "📊 Pattern detected: Every time you mention **sleep** in the same entry as **deadlines**, your sentiment drops to -0.6 average. These two topics together are a strong negative trigger."

### Technical Plan

**New service**: `backend/services/trigger_detector.py`

```python
def detect_triggers(user_id: str, days: int = 90) -> list[TriggerPattern]:
    """
    Scroll all entries for user.
    For each keyword that appears 3+ times:
      - Compute avg sentiment when keyword is present
      - Compute avg sentiment when keyword is absent
      - If difference > 0.2 (statistically meaningful) → flag as trigger
    
    For time-of-day:
      - Bucket entries by hour (morning/afternoon/evening/night)
      - Compare sentiment across buckets
      - If any bucket deviates by > 0.15 → flag as time trigger

    For keyword co-occurrence:
      - Find keyword pairs that appear together 3+ times
      - If co-occurrence sentiment is significantly lower than either alone → flag
    """
```

**Qdrant usage**: Scroll API with payload filtering — group by keywords, compute sentiment aggregates per keyword cluster. This is a novel use of Qdrant beyond simple similarity search.

**New endpoint**: `GET /api/triggers?user_id=&days=90`
Returns:
```json
{
  "triggers": [
    {
      "type": "keyword",
      "trigger": "Monday meetings",
      "avg_sentiment_with": -0.42,
      "avg_sentiment_without": 0.12,
      "impact": -0.54,
      "occurrences": 8,
      "confidence": "high"
    },
    {
      "type": "time",
      "trigger": "Late night (10PM-2AM)",
      "avg_sentiment": -0.31,
      "baseline_avg": 0.05,
      "impact": -0.36,
      "occurrences": 12,
      "confidence": "medium"
    },
    {
      "type": "co-occurrence",
      "trigger": "sleep + deadlines",
      "avg_sentiment_together": -0.58,
      "avg_sentiment_apart": -0.1,
      "impact": -0.48,
      "occurrences": 5,
      "confidence": "medium"
    }
  ]
}
```

**Dashboard**: New "Triggers" card in Insights tab
- Bar chart showing top 5 triggers ranked by impact
- Each bar shows: trigger name, impact score, occurrence count
- Color: red for negative triggers, green for positive triggers (e.g., "gym" → +0.4)
- Click to see all entries containing that trigger

**Telegram integration**: Weekly recap includes top trigger:
> "This week's insight: entries mentioning 'deadlines' were your most negative. Consider what you can delegate or reschedule."

**Vapi integration**: Agent references triggers in conversation:
> "I've noticed that sleep and deadlines seem to be a tough combination for you. When those come up together, your mood drops significantly. Are both of those happening right now?"

### Why Judges Will Love This
- Transforms passive journaling into **actionable intelligence**
- Shows Qdrant being used for **analytics**, not just retrieval
- The "co-occurrence" trigger detection is technically sophisticated
- Every user immediately thinks "I want to know MY triggers"
- Differentiator: Daylio shows "you rated Monday 2/5." We show "Monday meetings + sleep problems = your worst combination, and here's the data."

### Demo Script (45 seconds)
1. Open Karan's profile → Insights tab → Triggers card
2. Show: "deadlines" = -0.54 impact, 8 occurrences
3. Show: "sleep + deadlines" co-occurrence = -0.58
4. Show: "gym" = +0.4 (positive trigger!)
5. "The journal doesn't just record — it identifies what's hurting you and what's helping."

---

## Feature 4: Mood Trajectory Forecast

### The Insight
Your emotional patterns are more cyclical than you think. People in burnout follow predictable arcs. Recovery has a shape. Anxiety spikes have durations. If MoodDrift has 3 months of your data, it can recognize **where you are in a pattern you've been through before**.

This isn't prediction. It's **pattern recognition** — "you've been here before, and here's what happened next."

### What It Does

> "📈 Based on your entry patterns, this dip looks similar to what happened in February. That time, things started improving around day 5. You're on day 3. If the pattern holds, the next few days could feel heavy — but the trend points toward recovery."

> "⚠️ Heads up: historically, your mood dips in the last week of the month. This has happened in 3 of the last 4 months. This week might be tougher — be extra gentle with yourself."

### How It Works (Not Magic — Math)

```
1. HISTORICAL PATTERN MATCHING
   - Take current 7-day entry vectors
   - Search Qdrant for the most similar historical 7-day window
   - Look at what happened AFTER that historical window
   - If recovery followed → predict recovery
   - If deepening followed → warn

2. CYCLICAL ANALYSIS  
   - Score sentiment by week-of-month (1st, 2nd, 3rd, 4th)
   - Score sentiment by day-of-week
   - If consistent patterns emerge (3+ cycles) → forecast

3. TRAJECTORY FITTING
   - Fit a simple linear trend to last 14 days of sentiment
   - Positive slope = improving trajectory
   - Negative slope = declining trajectory
   - Rate of change indicates speed
```

### Technical Plan

**New service**: `backend/services/forecast.py`

```python
def generate_forecast(user_id: str) -> ForecastResult:
    # 1. Get current week's centroid
    # 2. Search Qdrant for most similar historical week (excluding recent)
    # 3. Look at the 7 days AFTER that historical match
    # 4. Compute sentiment trajectory of that "what happened next" window
    # 5. Compute cyclical patterns (day-of-week, week-of-month)
    # 6. Combine signals into forecast

    return ForecastResult(
        trajectory="improving" | "declining" | "stable",
        confidence=0.72,
        similar_period="Feb 10-17",
        what_happened_next="Recovery over 5 days, sentiment went from -0.3 to +0.2",
        cyclical_warning="Your mood typically dips in the last week of the month",
        message="This feels like mid-February. That time, things started improving around day 5. You're on day 3."
    )
```

**Qdrant usage**: Sliding window search — compute centroids for every 7-day window in history, find the closest match to current state. This is **temporal vector similarity at scale** — a novel Qdrant pattern.

**New endpoint**: `GET /api/forecast?user_id=`

**Dashboard**: "Forecast" card in Insights tab
- Simple arrow indicator: ↗️ improving, → stable, ↘️ declining
- Confidence percentage
- Historical comparison: "Similar to Feb 10-17 (you recovered in 5 days)"
- Cyclical warnings if applicable

**Telegram**: Included in weekly recap
> "Looking ahead: your current pattern matches mid-February. That time, recovery came on day 5. You're on day 3 — hang in there."

**Vapi**: Agent mentions forecast naturally
> "Based on your patterns, I think this week might be tough — but historically, you bounce back after about 5 days. What usually helps you push through?"

### Why Judges Will Love This
- **Nobody does this.** Mood apps show past. We show future trajectory.
- Technically impressive — sliding window vector comparison across temporal axis
- Clinically interesting — mood patterns ARE cyclical (menstrual cycles, work cycles, seasonal)
- Empowering for users — "this will pass" backed by THEIR OWN data
- Heavy Qdrant usage — exactly what the sponsor wants to see

### Demo Script (45 seconds)
1. Open Karan's profile (currently in April drift)
2. Show Forecast card: "This pattern matches February burnout. Recovery came on day 5. You're on day 3."
3. Show confidence: 72% based on pattern similarity
4. Show cyclical warning: "Your mood dips in the last week of the month — 3 of last 4 months"
5. "We don't predict the future. We show you YOUR patterns — and what happened next."

### Disclaimer
*Prominently displayed*: "This is pattern recognition based on your journal history, not a clinical prediction. Your experience may differ. If you're in crisis, please contact a mental health professional."

---

## Feature 5: Agent Memory — The Voice That Knows Your Story

### The Insight
Every Vapi call and every Telegram conversation starts from zero. The agent says "How are you feeling today?" with no context. No memory. No continuity.

Real therapists don't do this. Real friends don't do this. They say: *"Hey, last time you mentioned your deadline was this Friday — how did it go?"*

If MoodDrift's agent **remembers** — if it can reference last week's entries, follow up on unresolved threads, and acknowledge your journey — it stops being a tool and starts feeling like something that actually knows you.

### What It Does

**Before each conversation**, the agent retrieves the user's recent context from Qdrant and injects it into the system prompt:

Without memory:
> "Hi! How are you feeling today?"

With memory:
> "Hey Karan — last time we talked, you mentioned that deadline pressure was getting to you and you hadn't been sleeping well. You also said gym helped you decompress. How have things been since then?"

**Mid-conversation retrieval** (already partially built via `search_similar_past_entries`):
> User: "I'm stressed about work again"  
> Agent: "I remember — work stress was a big theme in February too. Back then, you said taking a full weekend offline was a turning point. Have you been able to do that recently?"

**Emotional continuity** — the agent tracks your arc:
> "I've noticed your entries have been getting more positive over the last 10 days. That's a real shift from two weeks ago. What do you think changed?"

### Technical Plan

**Modified Vapi system prompt** — dynamically generated per call:

```python
def build_agent_context(user_id: str) -> str:
    # 1. Get last 5 entries from Qdrant (scroll, sorted by timestamp)
    # 2. Get current drift status
    # 3. Get active triggers (from trigger detection)
    # 4. Get any time capsules available
    # 5. Compose into system prompt addendum

    return f"""
    CONTEXT ABOUT THIS USER (from their recent journal):
    - Last check-in ({last_entry.date}): "{last_entry.transcript[:200]}"
    - Recent themes: {', '.join(recent_keywords)}
    - Sentiment trend: {trend} (from {old_avg:.1f} to {new_avg:.1f})
    - Drift status: {drift.severity if drift.detected else 'stable'}
    - Known triggers: {triggers}
    - Available time capsule: {bool(capsules)}

    USE this context naturally. Reference specific things they said.
    Don't dump all context at once — weave it into conversation.
    Ask follow-up questions about unresolved threads.
    """
```

**Modified Telegram bot** — context-aware replies:

```python
async def process_entry(user_id, transcript):
    # After storing entry + drift check...
    # Compare with last entry
    last_entry = get_last_entry(user_id)

    if similar_themes(current, last_entry):
        reply += f"You mentioned {shared_theme} again — "
        reply += "that's been coming up a lot lately."

    if sentiment_improving(current, last_entry):
        reply += "Your tone feels lighter than last time. That's good to see."
```

**New endpoint**: `GET /api/context?user_id=` — returns structured context for agent injection

**Qdrant usage**: Scroll + filter for recent entries, keyword aggregation, sentiment trend computation — all in a single context-building call. Shows Qdrant as a **real-time context engine**, not just a vector store.

### Why Judges Will Love This
- Transforms a stateless voice agent into something that **feels alive**
- The "last time you mentioned..." moment is a guaranteed demo jaw-drop
- Shows deep Vapi + Qdrant integration — exactly what both sponsors want
- Technically clean — it's retrieval-augmented conversation, but for emotional context
- Users immediately feel understood — "this app KNOWS me"

### Demo Script (60 seconds)
1. Show Karan's recent entries (deadline stress, no sleep)
2. Start a Vapi call
3. Agent opens: "Hey Karan, last time you mentioned deadlines were crushing you and you hadn't been sleeping. How have things been?"
4. User responds: "Still stressed but I went to the gym yesterday"
5. Agent: "That's good — you've mentioned before that gym helps you decompress. Your entries have actually been slightly more positive the last couple days."
6. "The agent isn't reading a script. It's reading YOUR journal."

---

## Implementation Priority

| # | Feature | Effort | Impact | Qdrant Depth | Vapi Depth | Demo Wow |
|---|---|---|---|---|---|---|
| 1 | Agent Memory | 3-4 hrs | 🔥🔥🔥 | Deep (context retrieval) | Deep (dynamic prompt) | 🔥🔥🔥 |
| 2 | Voice Biomarkers | 4-5 hrs | 🔥🔥🔥 | Medium (payload storage) | Medium (references vocal data) | 🔥🔥🔥 |
| 3 | Trigger Detection | 3-4 hrs | 🔥🔥🔥 | Deep (analytics queries) | Medium (references triggers) | 🔥🔥 |
| 4 | Voice Time Capsule | 2-3 hrs | 🔥🔥 | Medium (tagged storage) | Medium (playback prompt) | 🔥🔥🔥 |
| 5 | Mood Forecast | 3-4 hrs | 🔥🔥 | Deep (sliding window) | Low (mentions forecast) | 🔥🔥 |

### Recommended Order
1. **Agent Memory** — highest ROI, makes every demo interaction better
2. **Trigger Detection** — most actionable insight, strong Qdrant showcase
3. **Voice Biomarkers** — biggest technical differentiator, requires librosa integration
4. **Voice Time Capsule** — emotional climax of the demo, relatively simple to build
5. **Mood Forecast** — impressive but depends on having good historical data

---

## Competitive Moat

| Competitor | What They Do | What They Can't Do |
|---|---|---|
| **Daylio** | Emoji mood rating, habit tracking | No voice, no drift detection, no AI analysis, no coping recall |
| **Reflectly** | AI text journaling, prompts | No voice input, no vector analysis, no pattern detection |
| **Woebot** | CBT chatbot, scripted flows | No memory, no voice biomarkers, no personalization from past entries |
| **Wysa** | CBT exercises, mood tracking | No semantic embedding, no drift, no time capsules |
| **Youper** | AI therapy conversations | No voice-first, no trigger detection, no forecast |
| **MoodDrift** | **All of the above + voice biomarkers, time capsules, trigger detection, mood forecast, agent memory** | — |

The gap is not incremental. It's structural. We're not building a better journaling app. We're building **the first journal that actually understands you** — through your words AND your voice.
