import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { useDriftTimeline } from "../hooks/useEntries";

export default function DriftTimeline() {
  const { timeline, loading } = useDriftTimeline();

  if (loading) return <div className="panel loading">Loading drift timeline…</div>;
  if (timeline.length === 0) return <div className="panel">Not enough data for timeline.</div>;

  return (
    <div className="panel">
      <h2>Drift Score Over Time</h2>
      <p className="panel-sub">Higher values mean your recent entries differ more from your baseline.</p>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={timeline} margin={{ top: 10, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="week_start"
            tick={{ fill: "#999", fontSize: 11 }}
            tickLine={false}
          />
          <YAxis
            domain={[0, "auto"]}
            tick={{ fill: "#999", fontSize: 11 }}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: "#1a1a2e",
              border: "1px solid #333",
              borderRadius: 8,
              fontSize: 13,
            }}
            labelStyle={{ color: "#999" }}
            formatter={(value) => [Number(value).toFixed(4), "Drift Score"]}
          />
          <ReferenceLine
            y={0.25}
            stroke="#ef4444"
            strokeDasharray="6 3"
            label={{ value: "Threshold", fill: "#ef4444", fontSize: 11, position: "right" }}
          />
          <Line
            type="monotone"
            dataKey="drift_score"
            stroke="#8b5cf6"
            strokeWidth={2}
            dot={{ fill: "#8b5cf6", r: 4 }}
            activeDot={{ r: 6, stroke: "#fff", strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
