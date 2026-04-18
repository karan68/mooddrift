import { useState, useRef, useCallback, useEffect } from "react";
import { useTimeCapsules } from "../hooks/useEntries";
import { submitTimeCapsule, getCapsuleAudioUrl } from "../utils/api";
import type { TimeCapsule } from "../utils/api";

/**
 * Voice Time Capsule — FEATURES.md Feature 2.
 *
 * "Record a message to your future self when you're doing well.
 *  Hear it back when things get tough."
 *
 * Shows: capsule readiness prompt, recorder, list of past capsules with playback.
 */
export default function TimeCapsulePanel() {
  const { data, loading, refresh } = useTimeCapsules();

  // Recorder state
  const [recStatus, setRecStatus] = useState<"idle" | "recording" | "preview" | "processing" | "done">("idle");
  const [recDuration, setRecDuration] = useState(0);
  const [recError, setRecError] = useState<string | null>(null);
  const [pendingBlob, setPendingBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [openDate, setOpenDate] = useState("");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Playback state
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (audioRef.current) audioRef.current.pause();
    };
  }, []);

  const startRecording = useCallback(async () => {
    setRecError(null);
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
          setRecError("Recording too short. Speak for at least 2 seconds.");
          setRecStatus("idle");
          return;
        }

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
  }, [refresh]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
  }, []);

  const resetRecorder = useCallback(() => {
    setRecStatus("idle");
    setRecError(null);
    setRecDuration(0);
    setPendingBlob(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setOpenDate("");
  }, [previewUrl]);

  const submitCapsule = useCallback(async () => {
    if (!pendingBlob) return;
    setRecStatus("processing");
    try {
      const result = await submitTimeCapsule(pendingBlob, undefined, openDate || undefined);
      if (result.error) {
        setRecError(result.error);
        setRecStatus("preview");
      } else {
        setRecStatus("done");
        setPendingBlob(null);
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
        refresh();
      }
    } catch (err: unknown) {
      setRecError(err instanceof Error ? err.message : "Failed to save capsule.");
      setRecStatus("preview");
    }
  }, [pendingBlob, openDate, previewUrl, refresh]);

  const retakeCapsule = useCallback(() => {
    setPendingBlob(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setRecError(null);
    setRecStatus("idle");
  }, [previewUrl]);

  const playCapsule = useCallback((capsule: TimeCapsule) => {
    if (!capsule.audio_filename) return;

    // Stop current playback
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    if (playingId === capsule.id) {
      setPlayingId(null);
      return;
    }

    const audio = new Audio(getCapsuleAudioUrl(capsule.audio_filename));
    audioRef.current = audio;
    setPlayingId(capsule.id);
    audio.play();
    audio.onended = () => setPlayingId(null);
    audio.onerror = () => setPlayingId(null);
  }, [playingId]);

  if (loading) {
    return <div className="panel loading">Loading time capsules...</div>;
  }

  const capsules = data?.capsules ?? [];
  const readiness = data?.capsule_ready;

  return (
    <div className="panel">
      <h2>Voice Time Capsule</h2>
      <p className="panel-sub">
        Record a message to your future self when you're feeling good.
        We'll play it back when you need it most.
      </p>

      {/* === Capsule-ready prompt === */}
      {readiness?.ready && recStatus === "idle" && (
        <div
          style={{
            marginTop: 12,
            padding: "14px 16px",
            background: "linear-gradient(135deg, rgba(139,92,246,0.1), rgba(236,72,153,0.08))",
            border: "1px solid rgba(139,92,246,0.3)",
            borderRadius: 12,
            color: "#e2d6ff",
          }}
        >
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
            {readiness.streak} good days in a row!
          </div>
          <div style={{ fontSize: 13, color: "#ccc", marginBottom: 10 }}>
            You're in a great place right now. Want to leave a message for
            future-you? Something to hear on a tough day.
          </div>
          <button
            onClick={startRecording}
            style={{
              padding: "8px 20px",
              background: "#8b5cf6",
              color: "#fff",
              border: "none",
              borderRadius: 20,
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            Record a Time Capsule
          </button>
        </div>
      )}

      {/* === Recorder UI === */}
      {recStatus === "recording" && (
        <div
          style={{
            marginTop: 14, padding: 16,
            background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.3)",
            borderRadius: 12, textAlign: "center",
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔴</div>
          <div style={{ fontSize: 14, color: "#ccc", marginBottom: 4 }}>
            Recording... {recDuration}s
          </div>
          <div style={{ fontSize: 12, color: "#999", marginBottom: 12 }}>
            Speak to your future self — what would you want to hear on a bad day?
          </div>
          <button onClick={stopRecording} style={{
            padding: "8px 24px", background: "#ef4444", color: "#fff",
            border: "none", borderRadius: 20, cursor: "pointer", fontSize: 13, fontWeight: 600,
          }}>
            Stop Recording
          </button>
        </div>
      )}

      {/* === Preview step: listen, pick date, retake or submit === */}
      {recStatus === "preview" && previewUrl && (
        <div
          style={{
            marginTop: 14, padding: 16,
            background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.3)",
            borderRadius: 12, textAlign: "center",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#a78bfa" }}>
            Review your time capsule ({recDuration}s)
          </div>
          <audio controls src={previewUrl} style={{ width: "100%", marginBottom: 12 }} />

          <div style={{ marginBottom: 14, textAlign: "left" }}>
            <label style={{ fontSize: 12, color: "#999", display: "block", marginBottom: 4 }}>
              When should this capsule open? (optional)
            </label>
            <input
              type="date"
              value={openDate}
              onChange={(e) => setOpenDate(e.target.value)}
              min={new Date(Date.now() + 86400000).toISOString().split("T")[0]}
              style={{
                width: "100%", padding: "8px 12px", borderRadius: 8,
                border: "1px solid #444", background: "#1a1a2e", color: "#ddd",
                fontSize: 13,
              }}
            />
            <div style={{ fontSize: 11, color: "#666", marginTop: 4 }}>
              {openDate
                ? `Opens on ${openDate}. You'll see a notification that day.`
                : "Leave empty to open anytime (or when drift is detected)."}
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
            <button onClick={retakeCapsule} style={{
              padding: "8px 20px", background: "transparent", color: "#999",
              border: "1px solid #444", borderRadius: 20, cursor: "pointer", fontSize: 13,
            }}>
              Retake
            </button>
            <button onClick={submitCapsule} style={{
              padding: "8px 24px", background: "#8b5cf6", color: "#fff",
              border: "none", borderRadius: 20, cursor: "pointer", fontSize: 13, fontWeight: 600,
            }}>
              Save Capsule
            </button>
          </div>
        </div>
      )}

      {recStatus === "processing" && (
        <div style={{
          marginTop: 14, padding: 16, textAlign: "center",
          background: "rgba(139,92,246,0.08)", border: "1px solid rgba(139,92,246,0.3)",
          borderRadius: 12,
        }}>
          <div style={{ fontSize: 22, marginBottom: 6 }}>Saving your capsule...</div>
          <div style={{ fontSize: 13, color: "#999" }}>Transcribing and storing</div>
        </div>
      )}

      {recStatus === "done" && (
        <div
          style={{
            marginTop: 14,
            padding: "14px 16px",
            background: "rgba(16,185,129,0.08)",
            border: "1px solid rgba(16,185,129,0.3)",
            borderRadius: 12,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 22, marginBottom: 6 }}>Time capsule saved</div>
          <div style={{ fontSize: 13, color: "#999", marginBottom: 10 }}>
            Your future self will thank you.
          </div>
          <button
            onClick={resetRecorder}
            style={{
              padding: "6px 16px",
              background: "transparent",
              color: "#10b981",
              border: "1px solid rgba(16,185,129,0.3)",
              borderRadius: 16,
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Done
          </button>
        </div>
      )}

      {recError && (
        <div style={{ color: "#ef4444", fontSize: 13, marginTop: 8, textAlign: "center" }}>
          {recError}
        </div>
      )}

      {/* === Always-available record button (when not prompted) === */}
      {!readiness?.ready && recStatus === "idle" && (
        <button
          onClick={startRecording}
          style={{
            marginTop: 14,
            padding: "8px 20px",
            background: "rgba(139,92,246,0.15)",
            color: "#a78bfa",
            border: "1px solid rgba(139,92,246,0.3)",
            borderRadius: 20,
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 500,
            display: "block",
            width: "100%",
          }}
        >
          Record a new time capsule
        </button>
      )}

      {/* === Capsule list === */}
      {capsules.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 14, color: "#999", marginBottom: 10 }}>
            Your Capsules ({capsules.length})
          </h3>
          {capsules.map((capsule) => (
            <CapsuleCard
              key={capsule.id}
              capsule={capsule}
              isPlaying={playingId === capsule.id}
              onPlay={() => playCapsule(capsule)}
            />
          ))}
        </div>
      )}

      {capsules.length === 0 && recStatus === "idle" && (
        <div
          style={{
            marginTop: 20,
            padding: 20,
            textAlign: "center",
            color: "#666",
            fontSize: 13,
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 8 }}>💌</div>
          No time capsules yet. Record one during a good period — your future self will appreciate it.
        </div>
      )}
    </div>
  );
}

function CapsuleCard({
  capsule,
  isPlaying,
  onPlay,
}: {
  capsule: TimeCapsule;
  isPlaying: boolean;
  onPlay: () => void;
}) {
  const sentimentColor =
    capsule.sentiment_at_recording > 0.3
      ? "#10b981"
      : capsule.sentiment_at_recording > 0
        ? "#f59e0b"
        : "#ef4444";

  return (
    <div
      style={{
        padding: "12px 14px",
        marginBottom: 8,
        background: isPlaying
          ? "rgba(139,92,246,0.12)"
          : "rgba(255,255,255,0.03)",
        border: `1px solid ${isPlaying ? "rgba(139,92,246,0.4)" : "#2a2a3e"}`,
        borderRadius: 10,
        transition: "all 0.2s",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 6,
        }}
      >
        <div style={{ fontSize: 12, color: "#888" }}>
          📅 {capsule.date}
          <span
            style={{
              marginLeft: 8,
              color: sentimentColor,
              fontWeight: 600,
            }}
          >
            mood: {capsule.sentiment_at_recording.toFixed(2)}
          </span>
          {capsule.open_date && (
            <span style={{ marginLeft: 8, color: "#a78bfa" }}>
              📬 opens {capsule.open_date}
            </span>
          )}
        </div>
        {capsule.has_audio && (
          <button
            onClick={onPlay}
            style={{
              padding: "4px 12px",
              background: isPlaying ? "#8b5cf6" : "rgba(139,92,246,0.15)",
              color: isPlaying ? "#fff" : "#a78bfa",
              border: "none",
              borderRadius: 14,
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            {isPlaying ? "⏹ Stop" : "▶ Play"}
          </button>
        )}
      </div>
      <div
        style={{
          fontSize: 13,
          color: "#ddd",
          lineHeight: 1.5,
          fontStyle: "italic",
        }}
      >
        "{capsule.transcript.slice(0, 200)}
        {capsule.transcript.length > 200 ? "..." : ""}"
      </div>
      {capsule.keywords.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#888" }}>
          {capsule.keywords.slice(0, 4).join(" · ")}
        </div>
      )}
    </div>
  );
}
