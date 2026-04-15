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
