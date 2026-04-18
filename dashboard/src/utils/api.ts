const API_BASE = "http://localhost:8000";

let _currentUser = "demo_user";

export function setCurrentUser(userId: string) {
  _currentUser = userId;
}

export function getCurrentUser() {
  return _currentUser;
}

export const USER_PROFILES: Record<string, { label: string; description: string; tooltip: string }> = {
  demo_user: {
    label: "Karan (Professional)",
    description: "Work burnout → recovery → new drift",
    tooltip: "Karan: Software engineer. Stable Jan → burnout Feb (overwork, insomnia) → recovery (took weekend off, set boundaries) → stable Mar → new drift Apr (deadline pressure). Demonstrates full drift detection + coping recall.",
  },
  student_ananya: {
    label: "Ananya (Student)",
    description: "Exam anxiety → isolation → finding balance",
    tooltip: "Ananya: College student. Confident Jan → midterm anxiety Feb (panic attacks, isolation, skipping meals) → counseling + friends → stable Mar → finals approaching Apr. Shows exam stress spiral + social support as coping.",
  },
  parent_rahul: {
    label: "Rahul (New Parent)",
    description: "Sleep deprivation → relationship strain → rhythm",
    tooltip: "Rahul: New father. Joy + exhaustion Jan → work guilt Feb (3hrs sleep, fights with wife) → asked for help, in-laws came → rhythm Mar → sleep regression Apr. Shows relationship strain + asking for help.",
  },
  athlete_priya: {
    label: "Priya (Athlete)",
    description: "Injury → frustration → rehab → comeback anxiety",
    tooltip: "Priya: Runner, ACL tear. Peak performance Jan → injury Feb (devastation, identity crisis) → rehab + coaching → strong comeback Mar → knee twinge anxiety Apr. Shows identity loss + gradual recovery.",
  },
  teacher_meera: {
    label: "Meera (Teacher) ✦",
    description: "Burnout → sabbatical → thriving",
    tooltip: "Meera: School teacher. Exhaustion + frustration Jan (overcrowded classes, no support) → took sabbatical Feb → traveled, journaled, rediscovered joy → returned Mar with new approach → thriving Apr. POSITIVE ARC — shows MoodDrift celebrating improvement.",
  },
};

export interface Entry {
  id: string;
  date: string;
  timestamp: number;
  transcript: string;
  sentiment_score: number;
  keywords: string[];
  entry_type: string;
}

export interface VisualizationPoint {
  id: string;
  x: number;
  y: number;
  date: string;
  sentiment_score: number;
  keywords: string[];
  transcript: string;
}

export interface DriftTimelinePoint {
  week: string;
  week_start: string;
  drift_score: number;
  avg_sentiment: number;
  entry_count: number;
}

export interface DriftCurrent {
  detected: boolean;
  drift_score: number;
  similarity: number;
  severity: string;
  message: string;
  matching_period: string | null;
  matching_context: string[] | null;
  sentiment_direction: string;
  skipped: boolean;
  skip_reason: string | null;
}

export async function fetchEntries(days = 90): Promise<Entry[]> {
  const res = await fetch(`${API_BASE}/api/entries?user_id=${_currentUser}&days=${days}`);
  const data = await res.json();
  return data.entries;
}

export async function fetchVisualization(days = 90): Promise<VisualizationPoint[]> {
  const res = await fetch(`${API_BASE}/api/visualization?user_id=${_currentUser}&days=${days}`);
  const data = await res.json();
  return data.points;
}

export async function fetchDriftTimeline(days = 90): Promise<DriftTimelinePoint[]> {
  const res = await fetch(`${API_BASE}/api/drift-timeline?user_id=${_currentUser}&days=${days}`);
  const data = await res.json();
  return data.timeline;
}

export async function fetchDriftCurrent(): Promise<DriftCurrent> {
  const res = await fetch(`${API_BASE}/api/drift-current?user_id=${_currentUser}`);
  return await res.json();
}

export async function fetchReport(days = 14): Promise<any> {
  const res = await fetch(`${API_BASE}/api/report?user_id=${_currentUser}&days=${days}`);
  return await res.json();
}

export interface VoiceBiomarkerPoint {
  id: string;
  date: string;
  timestamp: number;
  text_sentiment: number;
  vocal_stress_score: number;
  pitch_mean: number | null;
  pitch_std: number | null;
  speech_rate: number | null;
  pause_ratio: number | null;
  energy_mean: number | null;
  jitter: number | null;
  audio_duration: number | null;
  text_voice_congruence: number | null;
  voice_incongruent: boolean;
  transcript: string;
}

export interface VoiceBiomarkerBaselineStat {
  mean: number;
  std: number;
  count: number;
}

export interface VoiceBiomarkerResponse {
  timeline: VoiceBiomarkerPoint[];
  baseline: Record<string, VoiceBiomarkerBaselineStat> | null;
  latest_incongruence: VoiceBiomarkerPoint | null;
  summary: {
    total_voice_entries: number;
    incongruent_count: number;
    avg_vocal_stress: number | null;
    avg_congruence: number | null;
  };
}

export async function fetchVoiceBiomarkers(days = 90): Promise<VoiceBiomarkerResponse> {
  const res = await fetch(
    `${API_BASE}/api/voice-biomarkers?user_id=${_currentUser}&days=${days}`,
  );
  return await res.json();
}

export interface VoiceEntryResult {
  id: string;
  transcript: string;
  sentiment_score: number;
  keywords: string[];
  biomarkers: Record<string, number> | null;
  congruence: {
    congruence_score: number;
    incongruent: boolean;
    direction: string;
    message: string | null;
    vocal_stress_z: number | null;
  } | null;
  drift: DriftCurrent;
  error?: string;
}

export async function submitVoiceEntry(audioBlob: Blob): Promise<VoiceEntryResult> {
  const form = new FormData();
  form.append("audio", audioBlob, "recording.webm");
  form.append("user_id", _currentUser);
  form.append("entry_type", "checkin");
  const res = await fetch(`${API_BASE}/api/voice-entry`, {
    method: "POST",
    body: form,
  });
  return await res.json();
}

// === Time Capsule ===

export interface TimeCapsule {
  id: string;
  date: string;
  timestamp: number;
  transcript: string;
  sentiment_at_recording: number;
  audio_filename: string | null;
  has_audio: boolean;
  keywords: string[];
  open_date: string | null;
}

export interface CapsuleReadiness {
  ready: boolean;
  streak: number;
  avg_sentiment: number;
  message: string | null;
  already_has_recent: boolean;
}

export interface TimeCapsuleListResponse {
  capsules: TimeCapsule[];
  total: number;
  capsule_ready: CapsuleReadiness;
}

export async function fetchTimeCapsules(days = 180): Promise<TimeCapsuleListResponse> {
  const res = await fetch(
    `${API_BASE}/api/time-capsules?user_id=${_currentUser}&days=${days}`,
  );
  return await res.json();
}

export async function submitTimeCapsule(audioBlob: Blob | null, transcript?: string, openDate?: string): Promise<{ id: string; transcript: string; sentiment: number; has_audio: boolean; error?: string }> {
  const form = new FormData();
  if (audioBlob) form.append("audio", audioBlob, "capsule.webm");
  if (transcript) form.append("transcript", transcript);
  if (openDate) form.append("open_date", openDate);
  form.append("user_id", _currentUser);
  const res = await fetch(`${API_BASE}/api/time-capsule`, {
    method: "POST",
    body: form,
  });
  return await res.json();
}

export function getCapsuleAudioUrl(audioFilename: string): string {
  return `${API_BASE}/api/time-capsule/${audioFilename}/audio`;
}

export async function fetchCapsuleNotifications(): Promise<{ capsules: TimeCapsule[]; count: number; has_notifications: boolean }> {
  const res = await fetch(`${API_BASE}/api/time-capsule/notifications?user_id=${_currentUser}`);
  return await res.json();
}

export async function deleteEntry(entryId: string): Promise<{ deleted: boolean }> {
  const res = await fetch(`${API_BASE}/api/entries/${entryId}`, { method: "DELETE" });
  return await res.json();
}

export async function updateEntry(entryId: string, transcript: string): Promise<{ id: string; transcript: string; sentiment_score: number; keywords: string[] }> {
  const res = await fetch(`${API_BASE}/api/entries/${entryId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
  return await res.json();
}

// === Trigger Detection ===

export interface TriggerItem {
  type: "keyword" | "time" | "co-occurrence";
  trigger: string;
  impact: number;
  occurrences: number;
  confidence: "high" | "medium" | "low";
  avg_sentiment_with?: number;
  avg_sentiment_without?: number;
  avg_sentiment?: number;
  baseline_avg?: number;
  avg_sentiment_together?: number;
  avg_sentiment_apart?: number;
  keywords?: string[];
}

export interface TriggerResponse {
  keyword_triggers: TriggerItem[];
  time_triggers: TriggerItem[];
  cooccurrence_triggers: TriggerItem[];
  total_entries_analyzed: number;
  analysis_window_days: number;
}

export async function fetchTriggers(days = 90): Promise<TriggerResponse> {
  const res = await fetch(`${API_BASE}/api/triggers?user_id=${_currentUser}&days=${days}`);
  return await res.json();
}
