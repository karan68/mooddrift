import { useVisualization } from "../hooks/useEntries";
import type { VisualizationPoint } from "../utils/api";
import { useState } from "react";

function sentimentColor(score: number): string {
  if (score > 0.3) return "#22c55e";
  if (score > 0) return "#86efac";
  if (score > -0.3) return "#fbbf24";
  return "#ef4444";
}

function dateOpacity(date: string): number {
  // More recent = more opaque
  const d = new Date(date).getTime();
  const now = Date.now();
  const ninetyDays = 90 * 86400000;
  const age = now - d;
  return Math.max(0.3, 1 - age / ninetyDays);
}

export default function ScatterPlot() {
  const { points, loading } = useVisualization();
  const [hovered, setHovered] = useState<VisualizationPoint | null>(null);

  if (loading) return <div className="panel loading">Loading scatter plot…</div>;
  if (points.length === 0) return <div className="panel">Not enough data for visualization.</div>;

  // Compute bounds
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const pad = 40;
  const w = 600, h = 400;

  return (
    <div className="panel">
      <h2>Emotional Landscape</h2>
      <p className="panel-sub">Each dot is a journal entry. Color = sentiment. Clusters = similar emotional states.</p>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: "auto" }}>
        <rect width={w} height={h} fill="transparent" />
        {points.map((p) => {
          const cx = pad + ((p.x - xMin) / xRange) * (w - 2 * pad);
          const cy = pad + ((p.y - yMin) / yRange) * (h - 2 * pad);
          const isHovered = hovered?.id === p.id;
          return (
            <circle
              key={p.id}
              cx={cx}
              cy={cy}
              r={isHovered ? 8 : 5}
              fill={sentimentColor(p.sentiment_score)}
              opacity={dateOpacity(p.date)}
              stroke={isHovered ? "#fff" : "none"}
              strokeWidth={isHovered ? 2 : 0}
              style={{ cursor: "pointer", transition: "r 0.15s, stroke-width 0.15s" }}
              onMouseEnter={() => setHovered(p)}
              onMouseLeave={() => setHovered(null)}
            />
          );
        })}
      </svg>
      {hovered && (
        <div className="tooltip">
          <strong>{hovered.date}</strong> &mdash; sentiment: {hovered.sentiment_score.toFixed(2)}
          <br />
          <span className="tooltip-text">"{hovered.transcript}"</span>
        </div>
      )}
      <div className="legend">
        <span><span className="dot" style={{ background: "#22c55e" }}></span> Positive</span>
        <span><span className="dot" style={{ background: "#fbbf24" }}></span> Neutral</span>
        <span><span className="dot" style={{ background: "#ef4444" }}></span> Negative</span>
      </div>
    </div>
  );
}
