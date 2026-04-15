import { useEntries, useDriftCurrent } from "../hooks/useEntries";

function severityBadge(severity: string) {
  const colors: Record<string, { bg: string; text: string }> = {
    none: { bg: "#ecfdf5", text: "#059669" },
    mild: { bg: "#fef3c7", text: "#b45309" },
    moderate: { bg: "#ffedd5", text: "#c2410c" },
    significant: { bg: "#fef2f2", text: "#dc2626" },
  };
  const c = colors[severity] || colors.none;
  return (
    <span className="badge" style={{ background: c.bg, color: c.text }}>
      {severity === "none" ? "Stable" : severity.charAt(0).toUpperCase() + severity.slice(1) + " drift"}
    </span>
  );
}

function sentimentBar(score: number) {
  const pct = ((score + 1) / 2) * 100;
  const color = score > 0.3 ? "#22c55e" : score > 0 ? "#86efac" : score > -0.3 ? "#fbbf24" : "#ef4444";
  return (
    <div className="sentiment-bar-track">
      <div className="sentiment-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export default function EntryList() {
  const { entries, loading: entriesLoading } = useEntries();
  const { drift, loading: driftLoading } = useDriftCurrent();

  return (
    <div className="panel entry-list-panel">
      <div className="entry-list-header">
        <h2>Journal Entries</h2>
        {!driftLoading && drift && (
          <div className="drift-badge-row">
            {severityBadge(drift.severity)}
            {drift.detected && (
              <span className="drift-score-label">
                Score: {drift.drift_score.toFixed(3)}
              </span>
            )}
          </div>
        )}
      </div>
      {!driftLoading && drift && drift.detected && (
        <div className="drift-message">{drift.message}</div>
      )}
      {entriesLoading ? (
        <div className="loading">Loading entries…</div>
      ) : (
        <div className="entry-scroll">
          {entries.map((entry) => (
            <div key={entry.id} className="entry-card">
              <div className="entry-meta">
                <span className="entry-date">{entry.date}</span>
                {sentimentBar(entry.sentiment_score)}
                <span className="entry-sentiment">{entry.sentiment_score > 0 ? "+" : ""}{entry.sentiment_score.toFixed(2)}</span>
              </div>
              <p className="entry-transcript">{entry.transcript}</p>
              {entry.keywords.length > 0 && (
                <div className="entry-keywords">
                  {entry.keywords.map((kw) => (
                    <span key={kw} className="keyword-tag">{kw}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
