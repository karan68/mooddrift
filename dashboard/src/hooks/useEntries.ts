import { useState, useEffect, useCallback } from "react";
import {
  fetchEntries,
  fetchVisualization,
  fetchDriftTimeline,
  fetchDriftCurrent,
  type Entry,
  type VisualizationPoint,
  type DriftTimelinePoint,
  type DriftCurrent,
} from "../utils/api";

const POLL_INTERVAL = 5000; // 5 seconds — per Fix 1 in PROJECT.md

export function useEntries(days = 90) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchEntries(days).then(setEntries).finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  return { entries, loading };
}

export function useVisualization(days = 90) {
  const [points, setPoints] = useState<VisualizationPoint[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchVisualization(days).then(setPoints).finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  return { points, loading };
}

export function useDriftTimeline(days = 90) {
  const [timeline, setTimeline] = useState<DriftTimelinePoint[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchDriftTimeline(days).then(setTimeline).finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  return { timeline, loading };
}

export function useDriftCurrent() {
  const [drift, setDrift] = useState<DriftCurrent | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchDriftCurrent().then(setDrift).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  return { drift, loading };
}
