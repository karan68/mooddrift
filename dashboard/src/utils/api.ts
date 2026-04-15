const API_BASE = "http://localhost:8000";

let _currentUser = "demo_user";

export function setCurrentUser(userId: string) {
  _currentUser = userId;
}

export function getCurrentUser() {
  return _currentUser;
}

export const USER_PROFILES: Record<string, { label: string; description: string }> = {
  demo_user: { label: "Karan (Professional)", description: "Work burnout → recovery → new drift" },
  student_ananya: { label: "Ananya (Student)", description: "Exam anxiety → isolation → finding balance" },
  parent_rahul: { label: "Rahul (New Parent)", description: "Sleep deprivation → relationship strain → rhythm" },
  athlete_priya: { label: "Priya (Athlete)", description: "Injury → frustration → rehab → comeback anxiety" },
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
