import { useState, useRef, useCallback, useEffect } from "react";
import Vapi from "@vapi-ai/web";

const VAPI_PUBLIC_KEY = "8e36f2c2-6616-4094-a1d8-5d7c937f10aa";

interface TranscriptLine {
  role: "assistant" | "user";
  text: string;
}

export default function VoiceCheckin({ assistantId }: { assistantId?: string }) {
  const [status, setStatus] = useState<"idle" | "connecting" | "active" | "ended">("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [volume, setVolume] = useState(0);
  const vapiRef = useRef<Vapi | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

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

  return (
    <div className="checkin-panel">
      <div className="checkin-header">
        <h2>Daily Check-in</h2>
        <p className="checkin-sub">
          {status === "idle" && "Tap the mic to start your voice journal entry."}
          {status === "connecting" && "Connecting…"}
          {status === "active" && "Listening — speak freely about how you're feeling."}
          {status === "ended" && "Check-in complete. Your entry has been stored."}
        </p>
      </div>

      <div className="checkin-body">
        {/* Mic button */}
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

        {/* Live transcript */}
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
      </div>

      {!assistantId && (
        <p className="checkin-note">
          Voice check-in requires a Vapi assistant. Set VAPI_ASSISTANT_ID in your environment.
          You can still explore the dashboard with seeded data.
        </p>
      )}
    </div>
  );
}
