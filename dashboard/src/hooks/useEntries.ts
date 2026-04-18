import { useState, useEffect, useCallback } from "react";
import {
  fetchEntries,
  fetchVisualization,
  fetchDriftTimeline,
  fetchDriftCurrent,
  fetchVoiceBiomarkers,
  fetchTimeCapsules,
  fetchTriggers,
  getCurrentUser,
  type Entry,
  type VisualizationPoint,
  type DriftTimelinePoint,
  type DriftCurrent,
  type VoiceBiomarkerResponse,
  type TimeCapsuleListResponse,
  type TriggerResponse,
} from "../utils/api";

const POLL_INTERVAL = 10000; // 10 seconds for things that should poll

export function useEntries(days = 90) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchEntries(days).then(setEntries).finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  return { entries, loading };
}

export function useVisualization(days = 90) {
  const [points, setPoints] = useState<VisualizationPoint[]>([]);
  const [loading, setLoading] = useState(true);

  // NO polling — fetch once, it's expensive (UMAP)
  useEffect(() => {
    setLoading(true);
    fetchVisualization(days).then(setPoints).finally(() => setLoading(false));
  }, [days]);

  return { points, loading };
}

export function useDriftTimeline(days = 90) {
  const [timeline, setTimeline] = useState<DriftTimelinePoint[]>([]);
  const [loading, setLoading] = useState(true);

  // NO polling — fetch once per tab switch
  useEffect(() => {
    setLoading(true);
    fetchDriftTimeline(days).then(setTimeline).finally(() => setLoading(false));
  }, [days]);

  return { timeline, loading };
}

export function useDriftCurrent() {
  const [drift, setDrift] = useState<DriftCurrent | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchDriftCurrent().then(setDrift).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh();
    const id = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [refresh]);

  return { drift, loading };
}

export function useVoiceBiomarkers(days = 90) {
  const [data, setData] = useState<VoiceBiomarkerResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // No polling — voice biomarker data only changes when a new voice note arrives.
  useEffect(() => {
    setLoading(true);
    fetchVoiceBiomarkers(days)
      .then(setData)
      .finally(() => setLoading(false));
  }, [days]);

  return { data, loading };
}

export function useTimeCapsules(days = 180) {
  const [data, setData] = useState<TimeCapsuleListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    fetchTimeCapsules(days).then(setData).finally(() => setLoading(false));
  }, [days]);

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [refresh]);

  return { data, loading, refresh };
}

export function useTriggers(days = 90) {
  const [data, setData] = useState<TriggerResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchTriggers(days).then(setData).finally(() => setLoading(false));
  }, [days]);

  return { data, loading };
}
