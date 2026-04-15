import { useDriftCurrent } from "../hooks/useEntries";

export default function InsightCard() {
  const { drift, loading } = useDriftCurrent();

  if (loading) {
    return (
      <div className="insight-card insight-card--loading">
        <p>Analyzing your emotional patterns…</p>
      </div>
    );
  }

  if (!drift || drift.skipped) {
    const reason = drift?.skip_reason || "";
    const isNew = reason.includes("recent") || reason.includes("baseline");
    return (
      <div className="insight-card insight-card--calibrating">
        <div className="insight-icon">🌱</div>
        <div className="insight-content">
          <h2>Building your baseline</h2>
          <p>
            Keep checking in daily. MoodDrift needs about 2 weeks of entries
            to start recognizing your emotional patterns.
          </p>
          {isNew && <p className="insight-detail">{drift?.message}</p>}
        </div>
      </div>
    );
  }

  if (drift.detected) {
    const icon = drift.sentiment_direction === "improving" ? "🌤️" : "⚠️";
    const tone = drift.sentiment_direction === "improving" ? "positive" : "alert";
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
          <p className="insight-message">{drift.message}</p>
          {drift.matching_period && (
            <div className="insight-meta">
              <span className="insight-period">Pattern match: {drift.matching_period}</span>
              {drift.matching_context && drift.matching_context.length > 0 && (
                <span className="insight-themes">
                  Themes: {drift.matching_context.slice(0, 3).join(", ")}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="insight-score">
          <div className="insight-score-value">{(drift.drift_score * 100).toFixed(0)}</div>
          <div className="insight-score-label">drift</div>
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
          Your recent entries are consistent with your baseline.
          Keep up the practice — patterns become clearer over time.
        </p>
      </div>
    </div>
  );
}
