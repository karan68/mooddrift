import { useState, useRef, useCallback, useEffect } from "react";
import VapiModule from "@vapi-ai/web";
import { submitVoiceEntry } from "../utils/api";
import type { VoiceEntryResult } from "../utils/api";

// Handle CJS/ESM interop — the SDK may export { default: Vapi } or Vapi directly
const Vapi = (typeof VapiModule === "function" ? VapiModule : (VapiModule as any).default) as new (key: string) => any;

const VAPI_PUBLIC_KEY = "8e36f2c2-6616-4094-a1d8-5d7c937f10aa";

interface TranscriptLine {
  role: "assistant" | "user";
  text: string;
}

type CheckinMode = "vapi" | "record";

export default function VoiceCheckin({ assistantId }: { assistantId?: string }) {
  // === Shared state ===
  const [mode, setMode] = useState<CheckinMode>(assistantId ? "vapi" : "record");

  // === Vapi state ===
  const [status, setStatus] = useState<"idle" | "connecting" | "active" | "ended">("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [volume, setVolume] = useState(0);
  const vapiRef = useRef<Vapi | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // === Recorder state ===
  const [recStatus, setRecStatus] = useState<"idle" | "recording" | "preview" | "processing" | "done">("idle");
  const [recResult, setRecResult] = useState<VoiceEntryResult | null>(null);
  const [recError, setRecError] = useState<string | null>(null);
  const [recDuration, setRecDuration] = useState(0);
  const [pendingBlob, setPendingBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const startCall = useCallback(() => {
    if (!assistantId) return;

    const vapi = new Vapi(VAPI_PUBLIC_KEY);
    vapiRef.current = vapi;
    setStatus("connecting");
    setTranscript([]);

    vapi.on("call-start", () => setStatus("active"));

    vapi.on("call-end", () => {
      setStatus("ended");
      setVolume(0);
    });

    vapi.on("message", (msg: any) => {
      if (msg.type === "transcript" && msg.transcriptType === "final") {
        setTranscript((prev) => [
          ...prev,
          { role: msg.role, text: msg.transcript },
        ]);
      }
    });

    vapi.on("volume-level", (v: number) => setVolume(v));

    vapi.on("error", (err: any) => {
      console.error("Vapi error:", err);
      setStatus("idle");
    });

    vapi.start(assistantId);
  }, [assistantId]);

  const endCall = useCallback(() => {
    vapiRef.current?.stop();
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setTranscript([]);
    setVolume(0);
  }, []);

  // === Browser voice recorder (for biomarker analysis) ===
  const startRecording = useCallback(async () => {
    setRecError(null);
    setRecResult(null);
    setRecDuration(0);
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        if (timerRef.current) clearInterval(timerRef.current);

        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size < 1000) {
          setRecError("Recording too short. Try speaking for at least 2 seconds.");
          setRecStatus("idle");
          return;
        }

        // Go to preview — let user retake or submit
        setPendingBlob(blob);
        setPreviewUrl(URL.createObjectURL(blob));
        setRecStatus("preview");
      };

      recorder.start(250);
      setRecStatus("recording");
      timerRef.current = setInterval(() => setRecDuration((d) => d + 1), 1000);
    } catch {
      setRecError("Microphone access denied. Please allow mic permissions.");
    }
  }, []);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
  }, []);

  const resetRecorder = useCallback(() => {
    setRecStatus("idle");
    setRecResult(null);
    setRecError(null);
    setRecDuration(0);
    setPendingBlob(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
  }, [previewUrl]);

  const submitRecording = useCallback(async () => {
    if (!pendingBlob) return;
    setRecStatus("processing");
    try {
      const result = await submitVoiceEntry(pendingBlob);
      if (result.error) {
        setRecError(result.error);
        setRecStatus("preview");
      } else {
        setRecResult(result);
        setRecStatus("done");
        setPendingBlob(null);
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
    } catch (err: unknown) {
      setRecError(err instanceof Error ? err.message : "Failed to process voice entry.");
      setRecStatus("preview");
    }
  }, [pendingBlob, previewUrl]);

  const retakeRecording = useCallback(() => {
    setPendingBlob(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setRecError(null);
    setRecStatus("idle");
  }, [previewUrl]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  return (
    <div className="checkin-panel">
      <div className="checkin-header">
        <h2>Daily Check-in</h2>

        {/* Mode toggle */}
        <div style={{ display: "flex", gap: 8, justifyContent: "center", margin: "8px 0" }}>
          <button
            className={`mode-toggle ${mode === "record" ? "mode-toggle--active" : ""}`}
            onClick={() => { setMode("record"); reset(); resetRecorder(); }}
            style={{
              padding: "4px 14px", borderRadius: 16, border: "1px solid #ddd",
              background: mode === "record" ? "#6C5CE7" : "transparent",
              color: mode === "record" ? "#fff" : "#666", cursor: "pointer",
              fontSize: 13, fontWeight: 500,
            }}
          >
            🎤 Voice Note
          </button>
          {assistantId && (
            <button
              className={`mode-toggle ${mode === "vapi" ? "mode-toggle--active" : ""}`}
              onClick={() => { setMode("vapi"); resetRecorder(); }}
              style={{
                padding: "4px 14px", borderRadius: 16, border: "1px solid #ddd",
                background: mode === "vapi" ? "#6C5CE7" : "transparent",
                color: mode === "vapi" ? "#fff" : "#666", cursor: "pointer",
                fontSize: 13, fontWeight: 500,
              }}
            >
              💬 Voice Call
            </button>
          )}
        </div>

        <p className="checkin-sub">
          {mode === "vapi" && status === "idle" && "Tap the mic to start a voice conversation."}
          {mode === "vapi" && status === "connecting" && "Connecting…"}
          {mode === "vapi" && status === "active" && "Listening — speak freely about how you're feeling."}
          {mode === "vapi" && status === "ended" && "Check-in complete. Your entry has been stored."}
          {mode === "record" && recStatus === "idle" && "Record a voice note. We'll analyze both your words and your voice."}
          {mode === "record" && recStatus === "recording" && `Recording… ${recDuration}s — tap to stop when you're done.`}
          {mode === "record" && recStatus === "preview" && "Listen back and decide — submit or retake."}
          {mode === "record" && recStatus === "processing" && "Analyzing your voice and words…"}
          {mode === "record" && recStatus === "done" && "Voice entry stored with biomarker analysis."}
        </p>
      </div>

      <div className="checkin-body">
        {/* === VAPI MODE === */}
        {mode === "vapi" && (
          <>
            <button
              className={`mic-btn mic-btn--${status}`}
              onClick={status === "idle" ? startCall : status === "active" ? endCall : reset}
              disabled={status === "connecting" || !assistantId}
              aria-label={status === "active" ? "End check-in" : "Start check-in"}
            >
              <div className="mic-ring" style={{ transform: `scale(${1 + volume * 0.5})` }} />
              {status === "active" ? (
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              ) : status === "ended" ? (
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : (
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <line x1="12" y1="19" x2="12" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              )}
            </button>

            {transcript.length > 0 && (
              <div className="transcript-box" ref={scrollRef}>
                {transcript.map((line, i) => (
                  <div key={i} className={`transcript-line transcript-line--${line.role}`}>
                    <span className="transcript-role">{line.role === "assistant" ? "MoodDrift" : "You"}</span>
                    <span className="transcript-text">{line.text}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* === RECORD MODE === */}
        {mode === "record" && (
          <>
            {/* Mic button — only for idle & recording states */}
            {(recStatus === "idle" || recStatus === "recording") && (
              <button
                className={`mic-btn mic-btn--${recStatus === "recording" ? "active" : "idle"}`}
                onClick={recStatus === "idle" ? startRecording : stopRecording}
                aria-label={recStatus === "recording" ? "Stop recording" : "Start recording"}
              >
                <div
                  className="mic-ring"
                  style={{
                    transform: `scale(${recStatus === "recording" ? 1.25 : 1})`,
                    transition: "transform 0.3s",
                  }}
                />
                {recStatus === "recording" ? (
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                ) : (
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    <line x1="12" y1="19" x2="12" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                )}
              </button>
            )}

            {/* === Preview step: retake / submit === */}
            {recStatus === "preview" && previewUrl && (
              <div style={{
                marginTop: 12, padding: 16, background: "rgba(108,92,231,0.06)",
                border: "1px solid rgba(108,92,231,0.2)", borderRadius: 12, textAlign: "center",
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#a78bfa" }}>
                  Review your recording ({recDuration}s)
                </div>
                <audio controls src={previewUrl} style={{ width: "100%", marginBottom: 12 }} />
                <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
                  <button onClick={retakeRecording} style={{
                    padding: "8px 20px", background: "transparent", color: "#999",
                    border: "1px solid #444", borderRadius: 20, cursor: "pointer", fontSize: 13,
                  }}>
                    Retake
                  </button>
                  <button onClick={submitRecording} style={{
                    padding: "8px 24px", background: "#6C5CE7", color: "#fff",
                    border: "none", borderRadius: 20, cursor: "pointer", fontSize: 13, fontWeight: 600,
                  }}>
                    Submit Entry
                  </button>
                </div>
              </div>
            )}

            {/* Processing spinner */}
            {recStatus === "processing" && (
              <div style={{ textAlign: "center", marginTop: 16 }}>
                <span style={{ fontSize: 32 }}>⏳</span>
                <div style={{ fontSize: 13, color: "#999", marginTop: 6 }}>Analyzing your voice and words...</div>
              </div>
            )}

            {recError && (
              <div style={{ color: "#e74c3c", fontSize: 13, marginTop: 8, textAlign: "center" }}>
                {recError}
              </div>
            )}

            {/* === Voice entry result card (after submit) === */}
            {recStatus === "done" && recResult && (
              <div style={{
                marginTop: 16, padding: 16, background: "rgba(108,92,231,0.06)",
                border: "1px solid rgba(108,92,231,0.2)", borderRadius: 12, textAlign: "left",
              }}>
                <div style={{ fontSize: 13, color: "#888", marginBottom: 4 }}>Transcript</div>
                <div style={{ fontSize: 14, marginBottom: 12, lineHeight: 1.5 }}>
                  "{recResult.transcript}"
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
                  <MiniStat label="Sentiment" value={recResult.sentiment_score.toFixed(2)}
                    color={recResult.sentiment_score > 0.2 ? "#10b981" : recResult.sentiment_score < -0.2 ? "#ef4444" : "#f59e0b"} />
                  {recResult.biomarkers && (
                    <MiniStat label="Vocal Stress" value={recResult.biomarkers.vocal_stress_score?.toFixed(2) ?? "—"}
                      color={recResult.biomarkers.vocal_stress_score > 0.5 ? "#ef4444" : "#10b981"} />
                  )}
                  {recResult.congruence && (
                    <MiniStat label="Congruence" value={recResult.congruence.congruence_score.toFixed(2)}
                      color={recResult.congruence.incongruent ? "#ef4444" : "#10b981"} />
                  )}
                </div>

                {recResult.keywords.length > 0 && (
                  <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>
                    Themes: {recResult.keywords.join(", ")}
                  </div>
                )}

                {/* Incongruence alert */}
                {recResult.congruence?.incongruent && recResult.congruence.message && (
                  <div style={{
                    padding: "10px 12px", background: "rgba(239,68,68,0.08)",
                    border: "1px solid rgba(239,68,68,0.25)", borderRadius: 8,
                    fontSize: 13, color: "#fca5a5", marginTop: 8,
                  }}>
                    <strong>🎙️ Voice-text mismatch</strong>
                    <div style={{ marginTop: 4, color: "#ddd" }}>
                      {recResult.congruence.message}
                    </div>
                  </div>
                )}

                {recResult.biomarkers && !recResult.congruence?.incongruent && (
                  <div style={{
                    padding: "10px 12px", background: "rgba(16,185,129,0.08)",
                    border: "1px solid rgba(16,185,129,0.25)", borderRadius: 8,
                    fontSize: 13, color: "#6ee7b7", marginTop: 8,
                  }}>
                    ✓ Voice and text are aligned — your words match how you sound.
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {!assistantId && mode === "vapi" && (
        <p className="checkin-note">
          Voice check-in requires a Vapi assistant. Set VAPI_ASSISTANT_ID in your environment.
          You can still explore the dashboard with seeded data.
        </p>
      )}
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.03)", border: "1px solid #2a2a3e",
      borderRadius: 8, padding: "6px 8px", textAlign: "center",
    }}>
      <div style={{ color: "#888", fontSize: 10 }}>{label}</div>
      <div style={{ color, fontSize: 16, fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  );
}
