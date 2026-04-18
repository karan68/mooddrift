import { useState } from "react";
import { useEntries, useDriftCurrent } from "../hooks/useEntries";
import { deleteEntry, updateEntry } from "../utils/api";

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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this entry? This cannot be undone.")) return;
    setActionLoading(id);
    try {
      await deleteEntry(id);
      window.location.reload();
    } catch {
      alert("Failed to delete entry.");
    }
    setActionLoading(null);
  };

  const handleEdit = (id: string, transcript: string) => {
    setEditingId(id);
    setEditText(transcript);
  };

  const handleSaveEdit = async (id: string) => {
    if (!editText.trim()) return;
    setActionLoading(id);
    try {
      await updateEntry(id, editText.trim());
      setEditingId(null);
      window.location.reload();
    } catch {
      alert("Failed to update entry.");
    }
    setActionLoading(null);
  };

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

              {editingId === entry.id ? (
                <div style={{ margin: "8px 0" }}>
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    style={{
                      width: "100%", minHeight: 60, padding: 8, borderRadius: 8,
                      border: "1px solid #444", background: "#1a1a2e", color: "#ddd",
                      fontSize: 13, resize: "vertical",
                    }}
                  />
                  <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                    <button onClick={() => handleSaveEdit(entry.id)}
                      disabled={actionLoading === entry.id}
                      style={{
                        padding: "4px 14px", background: "#10b981", color: "#fff",
                        border: "none", borderRadius: 12, cursor: "pointer", fontSize: 12,
                      }}>
                      {actionLoading === entry.id ? "Saving..." : "Save"}
                    </button>
                    <button onClick={() => setEditingId(null)}
                      style={{
                        padding: "4px 14px", background: "transparent", color: "#999",
                        border: "1px solid #444", borderRadius: 12, cursor: "pointer", fontSize: 12,
                      }}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <p className="entry-transcript">{entry.transcript}</p>
              )}

              {entry.keywords.length > 0 && (
                <div className="entry-keywords">
                  {entry.keywords.map((kw) => (
                    <span key={kw} className="keyword-tag">{kw}</span>
                  ))}
                </div>
              )}

              {editingId !== entry.id && (
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  <button onClick={() => handleEdit(entry.id, entry.transcript)}
                    style={{
                      padding: "2px 10px", background: "transparent", color: "#888",
                      border: "1px solid #333", borderRadius: 10, cursor: "pointer", fontSize: 11,
                    }}>
                    Edit
                  </button>
                  <button onClick={() => handleDelete(entry.id)}
                    disabled={actionLoading === entry.id}
                    style={{
                      padding: "2px 10px", background: "transparent", color: "#ef4444",
                      border: "1px solid rgba(239,68,68,0.3)", borderRadius: 10, cursor: "pointer", fontSize: 11,
                    }}>
                    {actionLoading === entry.id ? "..." : "Delete"}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
