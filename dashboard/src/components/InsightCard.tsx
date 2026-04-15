import { useState } from "react";
import { useDriftCurrent } from "../hooks/useEntries";

export default function InsightCard() {
  const { drift, loading } = useDriftCurrent();
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="insight-card insight-card--loading">
        <p>Checking your patterns…</p>
      </div>
    );
  }

  if (!drift || drift.skipped) {
    return (
      <div className="insight-card insight-card--calibrating">
        <div className="insight-icon">🌱</div>
        <div className="insight-content">
          <h2>Building your baseline</h2>
          <p>
            Keep checking in daily. MoodDrift needs about 2 weeks of entries
            to start recognizing your emotional patterns.
          </p>
        </div>
      </div>
    );
  }

  if (drift.detected) {
    const icon = drift.sentiment_direction === "improving" ? "🌤️" : "⚠️";
    const tone = drift.sentiment_direction === "improving" ? "positive" : "alert";

    // Split message into headline (first sentence) and detail (rest)
    const firstDot = drift.message.indexOf(". ");
    const headline = firstDot > 0 ? drift.message.slice(0, firstDot + 1) : drift.message;
    const detail = firstDot > 0 ? drift.message.slice(firstDot + 2) : "";

    return (
      <div className={`insight-card insight-card--${tone}`}>
        <div className="insight-icon">{icon}</div>
        <div className="insight-content">
          <h2>
            {drift.sentiment_direction === "improving"
              ? "Things are looking up"
              : drift.severity === "mild"
                ? "A subtle shift"
                : drift.severity === "moderate"
                  ? "A noticeable change"
                  : "Something important"}
          </h2>
          <p className="insight-message">{headline}</p>
          {detail && (
            <>
              {expanded && <p className="insight-detail-text">{detail}</p>}
              <button
                className="insight-expand"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? "Show less" : "Read more"}
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  // Stable
  return (
    <div className="insight-card insight-card--stable">
      <div className="insight-icon">✦</div>
      <div className="insight-content">
        <h2>You're in a good place</h2>
        <p>
          Your recent entries feel steady. Keep checking in —
          patterns become clearer over time.
        </p>
      </div>
    </div>
  );
}
