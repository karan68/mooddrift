import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useVoiceBiomarkers } from "../hooks/useEntries";

/**
 * Voice vs Text — the X-factor panel from FEATURES.md Feature 1.
 *
 * Plots text sentiment and acoustic vocal stress on the same time axis so
 * users can see when their words and their voice tell different stories.
 * Incongruent points are highlighted as red markers.
 */
export default function VoiceBiomarkers() {
  const { data, loading } = useVoiceBiomarkers();

  if (loading) {
    return <div className="panel loading">Loading voice biomarkers…</div>;
  }

  if (!data || data.timeline.length === 0) {
    return (
      <div className="panel">
        <h2>Voice vs Text</h2>
        <p className="panel-sub">
          Send a voice note to{" "}
          <a
            href="https://t.me/MoodDriftBot"
            target="_blank"
            rel="noopener noreferrer"
          >
            @MoodDriftBot
          </a>{" "}
          to start building your vocal baseline. We'll listen to{" "}
          <em>how</em> you speak — not just what you say.
        </p>
      </div>
    );
  }

  const { timeline, baseline, latest_incongruence, summary } = data;

  // Recharts wants both series on the same data array. Each row already has
  // both fields. We add an "incongruent_marker" column for the scatter overlay
  // so it only renders points that are flagged as incongruent.
  const chartData = timeline.map((p) => ({
    date: p.date,
    text_sentiment: p.text_sentiment,
    vocal_stress_score: p.vocal_stress_score,
    incongruent_marker: p.voice_incongruent ? p.vocal_stress_score : null,
    transcript: p.transcript,
  }));

  return (
    <div className="panel">
      <h2>Voice vs Text</h2>
      <p className="panel-sub">
        Your words and your voice — side by side. When the two diverge, we
        flag it.
      </p>

      {/* === Headline incongruence callout === */}
      {latest_incongruence && (
        <div
          style={{
            marginTop: 12,
            padding: "12px 14px",
            background: "rgba(239, 68, 68, 0.08)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: 8,
            color: "#fca5a5",
            fontSize: 14,
          }}
        >
          <strong>🎙️ Voice-text mismatch on {latest_incongruence.date}</strong>
          <div style={{ marginTop: 6, color: "#ddd", fontSize: 13 }}>
            Text sentiment{" "}
            <strong>
              {(latest_incongruence.text_sentiment ?? 0).toFixed(2)}
            </strong>{" "}
            · vocal stress{" "}
            <strong>
              {(latest_incongruence.vocal_stress_score ?? 0).toFixed(2)}
            </strong>
            {latest_incongruence.transcript && (
              <div style={{ marginTop: 4, fontStyle: "italic", opacity: 0.8 }}>
                "{latest_incongruence.transcript}"
              </div>
            )}
          </div>
        </div>
      )}

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart
          data={chartData}
          margin={{ top: 10, right: 20, bottom: 5, left: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="date"
            tick={{ fill: "#999", fontSize: 11 }}
            tickLine={false}
          />
          <YAxis
            yAxisId="sentiment"
            domain={[-1, 1]}
            tick={{ fill: "#10b981", fontSize: 11 }}
            tickLine={false}
            width={36}
            label={{
              value: "Text",
              angle: -90,
              position: "insideLeft",
              fill: "#10b981",
              fontSize: 11,
            }}
          />
          <YAxis
            yAxisId="stress"
            orientation="right"
            domain={[0, 1]}
            tick={{ fill: "#f59e0b", fontSize: 11 }}
            tickLine={false}
            width={36}
            label={{
              value: "Voice",
              angle: 90,
              position: "insideRight",
              fill: "#f59e0b",
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={{
              background: "#1a1a2e",
              border: "1px solid #333",
              borderRadius: 8,
              fontSize: 13,
            }}
            labelStyle={{ color: "#999" }}
            formatter={(value: number | string, name: string) => {
              if (value === null || value === undefined) return ["—", name];
              return [Number(value).toFixed(3), name];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            yAxisId="sentiment"
            type="monotone"
            dataKey="text_sentiment"
            name="Text sentiment"
            stroke="#10b981"
            strokeWidth={2}
            dot={{ fill: "#10b981", r: 3 }}
          />
          <Line
            yAxisId="stress"
            type="monotone"
            dataKey="vocal_stress_score"
            name="Vocal stress"
            stroke="#f59e0b"
            strokeWidth={2}
            dot={{ fill: "#f59e0b", r: 3 }}
          />
          <Scatter
            yAxisId="stress"
            dataKey="incongruent_marker"
            name="Incongruent"
            fill="#ef4444"
            shape="diamond"
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* === Summary stats row === */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 10,
          marginTop: 14,
          fontSize: 12,
        }}
      >
        <Stat label="Voice entries" value={summary.total_voice_entries} />
        <Stat
          label="Mismatches"
          value={summary.incongruent_count}
          color={summary.incongruent_count > 0 ? "#ef4444" : undefined}
        />
        <Stat
          label="Avg stress"
          value={summary.avg_vocal_stress?.toFixed(2) ?? "—"}
        />
        <Stat
          label="Avg congruence"
          value={summary.avg_congruence?.toFixed(2) ?? "—"}
        />
      </div>

      {/* === Personal baseline (if computed) === */}
      {baseline && baseline.vocal_stress_score && (
        <div
          style={{
            marginTop: 14,
            padding: "10px 12px",
            background: "rgba(139, 92, 246, 0.08)",
            border: "1px solid rgba(139, 92, 246, 0.3)",
            borderRadius: 8,
            fontSize: 12,
            color: "#cbd5e1",
          }}
        >
          <strong style={{ color: "#a78bfa" }}>Your vocal baseline</strong>{" "}
          (n={baseline.vocal_stress_score.count}): mean stress{" "}
          {baseline.vocal_stress_score.mean.toFixed(3)} · σ{" "}
          {baseline.vocal_stress_score.std.toFixed(3)}
          {baseline.pitch_mean && (
            <>
              {" · "}avg pitch {baseline.pitch_mean.mean.toFixed(0)} Hz
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <div
      style={{
        background: "rgba(255,255,255,0.03)",
        border: "1px solid #2a2a3e",
        borderRadius: 8,
        padding: "8px 10px",
        textAlign: "center",
      }}
    >
      <div style={{ color: "#888", fontSize: 11 }}>{label}</div>
      <div
        style={{
          color: color ?? "#fff",
          fontSize: 18,
          fontWeight: 600,
          marginTop: 2,
        }}
      >
        {value}
      </div>
    </div>
  );
}
