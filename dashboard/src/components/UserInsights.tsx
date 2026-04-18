import { useEntries, useDriftCurrent, useTriggers } from "../hooks/useEntries";
import type { TriggerItem } from "../utils/api";

/**
 * User-friendly insights — designed for the person journaling, not their therapist.
 *
 * Principles:
 *   - Lead with what matters: drift alert first if detected
 *   - Show, don't tell: mood calendar is the hero
 *   - No noise: filter out generic words, show real triggers
 *   - Context over numbers: "You said X" > "score -0.4"
 *   - One weekly pulse, not three redundant cards
 */

export default function UserInsights() {
  const { entries, loading: entriesLoading } = useEntries(90);
  const { drift } = useDriftCurrent();
  const { data: triggers } = useTriggers(90);

  if (entriesLoading) {
    return <div className="panel loading">Loading your insights…</div>;
  }

  if (!entries || entries.length === 0) {
    return (
      <div className="panel">
        <h2>Your Insights</h2>
        <p className="panel-sub">Start journaling to see patterns emerge here.</p>
      </div>
    );
  }

  const now = new Date();
  const todayStr = now.toISOString().split("T")[0];

  // === Mood calendar data ===
  const dayMap = new Map<string, { avg: number; count: number }>();
  for (const e of entries) {
    const existing = dayMap.get(e.date);
    if (existing) {
      existing.avg = (existing.avg * existing.count + e.sentiment_score) / (existing.count + 1);
      existing.count++;
    } else {
      dayMap.set(e.date, { avg: e.sentiment_score, count: 1 });
    }
  }

  const calendarDays: { date: string; label: string; sentiment: number | null; count: number }[] = [];
  for (let i = 27; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const ds = d.toISOString().split("T")[0];
    const dayData = dayMap.get(ds);
    calendarDays.push({
      date: ds,
      label: d.getDate().toString(),
      sentiment: dayData ? dayData.avg : null,
      count: dayData ? dayData.count : 0,
    });
  }

  // === Weekly pulse (one unified metric) ===
  const thisWeekStart = new Date(now);
  thisWeekStart.setDate(thisWeekStart.getDate() - thisWeekStart.getDay());
  const lastWeekStart = new Date(thisWeekStart);
  lastWeekStart.setDate(lastWeekStart.getDate() - 7);

  const thisWeekEntries = entries.filter((e) => e.date >= thisWeekStart.toISOString().split("T")[0]);
  const lastWeekEntries = entries.filter((e) => {
    return e.date >= lastWeekStart.toISOString().split("T")[0] && e.date < thisWeekStart.toISOString().split("T")[0];
  });

  const thisWeekAvg = thisWeekEntries.length > 0
    ? thisWeekEntries.reduce((s, e) => s + e.sentiment_score, 0) / thisWeekEntries.length : null;
  const lastWeekAvg = lastWeekEntries.length > 0
    ? lastWeekEntries.reduce((s, e) => s + e.sentiment_score, 0) / lastWeekEntries.length : null;
  const weekDelta = thisWeekAvg !== null && lastWeekAvg !== null ? thisWeekAvg - lastWeekAvg : null;

  // === Best & hardest moment (actual transcript, not just a date) ===
  const recent = entries.filter((e) => {
    const daysAgo = (now.getTime() - new Date(e.date).getTime()) / 86400000;
    return daysAgo <= 30;
  });
  const sorted = [...recent].sort((a, b) => a.sentiment_score - b.sentiment_score);
  const hardestEntry = sorted.length > 0 ? sorted[0] : null;
  const bestEntry = sorted.length > 0 ? sorted[sorted.length - 1] : null;

  // === Streak ===
  let streak = 0;
  for (let i = 0; i < 90; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const ds = d.toISOString().split("T")[0];
    if (dayMap.has(ds)) streak++;
    else if (i > 0) break;
  }

  return (
    <div className="panel">
      <h2>Your Insights</h2>

      {/* === 1. DRIFT ALERT — top priority if detected === */}
      {drift && drift.detected && (
        <div style={{
          margin: "12px 0 16px", padding: "14px 16px", borderRadius: 12,
          background: drift.severity === "significant"
            ? "rgba(239,68,68,0.08)" : "rgba(251,191,36,0.08)",
          border: `1px solid ${drift.severity === "significant"
            ? "rgba(239,68,68,0.3)" : "rgba(251,191,36,0.3)"}`,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: drift.severity === "significant" ? "#fca5a5" : "#fbbf24", marginBottom: 6 }}>
            {drift.severity === "significant" ? "⚠️ Noticeable shift" : "🔔 Subtle shift"}
          </div>
          <div style={{ fontSize: 13, color: "#4a4540", lineHeight: 1.5 }}>
            {drift.message}
          </div>
        </div>
      )}

      {/* === 2. WEEKLY PULSE — one card, not three === */}
      <div style={{
        padding: "14px 16px", borderRadius: 12, marginTop: 12,
        background: "rgba(255,255,255,0.5)", border: "1px solid #e8e4de",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 12, color: "#6b6560" }}>This week</div>
            <div style={{
              fontSize: 22, fontWeight: 700, marginTop: 2,
              color: thisWeekAvg !== null ? moodColor(thisWeekAvg) : "#666",
            }}>
              {thisWeekAvg !== null ? moodWord(thisWeekAvg) : "No entries yet"}
            </div>
            <div style={{ fontSize: 11, color: "#7a756f", marginTop: 2 }}>
              {thisWeekEntries.length} {thisWeekEntries.length === 1 ? "entry" : "entries"}
              {streak > 1 && ` · ${streak}-day streak`}
            </div>
          </div>
          {weekDelta !== null && (
            <div style={{
              textAlign: "right", padding: "6px 12px", borderRadius: 8,
              background: weekDelta > 0.1 ? "rgba(16,185,129,0.1)"
                : weekDelta < -0.1 ? "rgba(239,68,68,0.1)" : "rgba(255,255,255,0.03)",
              fontSize: 12,
            }}>
              <div style={{
                fontSize: 18, fontWeight: 700,
                color: weekDelta > 0.1 ? "#10b981" : weekDelta < -0.1 ? "#ef4444" : "#6b6560",
              }}>
                {weekDelta > 0.1 ? "↗" : weekDelta < -0.1 ? "↘" : "→"}
              </div>
              <div style={{ color: "#6b6560", marginTop: 2 }}>
                vs last week
              </div>
            </div>
          )}
        </div>
      </div>

      {/* === 3. MOOD CALENDAR === */}
      <div style={{ marginTop: 20 }}>
        <h3 style={{ fontSize: 13, color: "#6b6560", marginBottom: 8 }}>Last 4 weeks</h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
          {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
            <div key={`hdr-${i}`} style={{ textAlign: "center", fontSize: 10, color: "#7a756f", marginBottom: 2 }}>{d}</div>
          ))}
          {calendarDays.map((day) => {
            const bg = day.sentiment === null ? "rgba(255,255,255,0.03)"
              : day.sentiment > 0.3 ? "#10b981"
              : day.sentiment > 0 ? "#86efac"
              : day.sentiment > -0.3 ? "#fbbf24"
              : "#ef4444";
            return (
              <div
                key={day.date}
                title={day.sentiment !== null
                  ? `${day.date}: mood ${day.sentiment.toFixed(2)} (${day.count} entries)`
                  : `${day.date}: no entry`}
                style={{
                  width: "100%", aspectRatio: "1", borderRadius: 6,
                  background: bg, opacity: day.sentiment === null ? 0.3 : 0.8,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, color: day.sentiment === null ? "#a09890" : "#fff",
                  fontWeight: day.date === todayStr ? 700 : 400,
                  border: day.date === todayStr ? "2px solid #a78bfa" : "none",
                }}
              >
                {day.label}
              </div>
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10, color: "#7a756f" }}>
          <span>🟢 Good</span><span>🟡 Okay</span><span>🟠 Mixed</span><span>🔴 Tough</span>
        </div>
      </div>

      {/* === 4. TRIGGER PATTERNS (powered by trigger detector) === */}
      {triggers && (triggers.keyword_triggers.length > 0 || triggers.cooccurrence_triggers.length > 0) && (() => {
        const negTriggers = triggers.keyword_triggers.filter((t) => t.impact < 0).slice(0, 3);
        const posTriggers = triggers.keyword_triggers.filter((t) => t.impact > 0).slice(0, 3);
        const coTriggers = triggers.cooccurrence_triggers.slice(0, 3);

        return (
          <div style={{ marginTop: 20 }}>
            <h3 style={{ fontSize: 13, color: "#6b6560", marginBottom: 10 }}>Your triggers</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {negTriggers.length > 0 && (
                <div style={{
                  padding: "10px 12px", borderRadius: 10,
                  background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.15)",
                }}>
                  <div style={{ fontSize: 11, color: "#ef4444", fontWeight: 600, marginBottom: 6 }}>
                    What drags you down
                  </div>
                  {negTriggers.map((t) => (
                    <TriggerRow key={t.trigger} trigger={t} />
                  ))}
                </div>
              )}
              {posTriggers.length > 0 && (
                <div style={{
                  padding: "10px 12px", borderRadius: 10,
                  background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.15)",
                }}>
                  <div style={{ fontSize: 11, color: "#10b981", fontWeight: 600, marginBottom: 6 }}>
                    What lifts you up
                  </div>
                  {posTriggers.map((t) => (
                    <TriggerRow key={t.trigger} trigger={t} />
                  ))}
                </div>
              )}
            </div>

            {/* Co-occurrence triggers — split into toxic and power combos */}
            {coTriggers.length > 0 && (() => {
              const toxicCombos = coTriggers.filter((t) => t.impact < 0);
              const powerCombos = coTriggers.filter((t) => t.impact > 0);
              return (
                <>
                  {toxicCombos.length > 0 && (
                    <div style={{
                      marginTop: 10, padding: "10px 12px", borderRadius: 10,
                      background: "rgba(239,68,68,0.05)", border: "1px solid rgba(239,68,68,0.15)",
                    }}>
                      <div style={{ fontSize: 11, color: "#ef4444", fontWeight: 600, marginBottom: 6 }}>
                        Toxic combinations
                      </div>
                      {toxicCombos.map((t) => (
                        <div key={t.trigger} style={{ fontSize: 12, color: "#4a4540", marginBottom: 4 }}>
                          <span style={{ color: "#ef4444" }}>⚡</span>{" "}
                          <strong>{t.trigger}</strong>
                          <span style={{ color: "#7a756f", fontSize: 10, marginLeft: 4 }}>
                            ({t.occurrences}× together · mood drops to {t.avg_sentiment_together?.toFixed(2)})
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {powerCombos.length > 0 && (
                    <div style={{
                      marginTop: 10, padding: "10px 12px", borderRadius: 10,
                      background: "rgba(16,185,129,0.05)", border: "1px solid rgba(16,185,129,0.15)",
                    }}>
                      <div style={{ fontSize: 11, color: "#10b981", fontWeight: 600, marginBottom: 6 }}>
                        Power combinations
                      </div>
                      {powerCombos.map((t) => (
                        <div key={t.trigger} style={{ fontSize: 12, color: "#4a4540", marginBottom: 4 }}>
                          <span style={{ color: "#10b981" }}>✨</span>{" "}
                          <strong>{t.trigger}</strong>
                          <span style={{ color: "#7a756f", fontSize: 10, marginLeft: 4 }}>
                            ({t.occurrences}× together · mood lifts to {t.avg_sentiment_together?.toFixed(2)})
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        );
      })()}

      {/* === 5. MOMENTS — actual words, not numbers === */}
      {(bestEntry || hardestEntry) && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 13, color: "#6b6560", marginBottom: 10 }}>This month in moments</h3>

          {hardestEntry && hardestEntry.sentiment_score < -0.2 && (
            <div style={{
              padding: "10px 14px", borderRadius: 10, marginBottom: 8,
              background: "rgba(239,68,68,0.04)", borderLeft: "3px solid #ef4444",
            }}>
              <div style={{ fontSize: 11, color: "#ef4444", marginBottom: 4 }}>
                Hardest · {hardestEntry.date}
              </div>
              <div style={{ fontSize: 13, color: "#4a4540", fontStyle: "italic", lineHeight: 1.5 }}>
                "{hardestEntry.transcript.slice(0, 120)}{hardestEntry.transcript.length > 120 ? "…" : ""}"
              </div>
            </div>
          )}

          {bestEntry && bestEntry.sentiment_score > 0.2 && (
            <div style={{
              padding: "10px 14px", borderRadius: 10,
              background: "rgba(16,185,129,0.04)", borderLeft: "3px solid #10b981",
            }}>
              <div style={{ fontSize: 11, color: "#10b981", marginBottom: 4 }}>
                Brightest · {bestEntry.date}
              </div>
              <div style={{ fontSize: 13, color: "#4a4540", fontStyle: "italic", lineHeight: 1.5 }}>
                "{bestEntry.transcript.slice(0, 120)}{bestEntry.transcript.length > 120 ? "…" : ""}"
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function moodColor(s: number): string {
  if (s > 0.3) return "#10b981";
  if (s > 0) return "#86efac";
  if (s > -0.3) return "#fbbf24";
  return "#ef4444";
}

function moodWord(s: number): string {
  if (s > 0.3) return "Good";
  if (s > 0) return "Okay";
  if (s > -0.3) return "Mixed";
  return "Tough";
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.5)", border: "1px solid #e8e4de",
      borderRadius: 10, padding: "10px 12px", textAlign: "center",
    }}>
      <div style={{ fontSize: 11, color: "#6b6560" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color, marginTop: 2 }}>{value}</div>
      <div style={{ fontSize: 11, color: "#7a756f", marginTop: 2 }}>{sub}</div>
    </div>
  );
}

function TriggerRow({ trigger }: { trigger: TriggerItem }) {
  const isNeg = trigger.impact < 0;
  const confidenceBadge = trigger.confidence === "high" ? "●" : trigger.confidence === "medium" ? "◐" : "○";
  return (
    <div style={{ fontSize: 12, color: "#4a4540", marginBottom: 4 }}>
      <span style={{ color: isNeg ? "#ef4444" : "#10b981" }}>•</span>{" "}
      {trigger.trigger}
      <span style={{ color: "#7a756f", fontSize: 10, marginLeft: 4 }}>
        {trigger.occurrences}× · {isNeg ? "" : "+"}{trigger.impact.toFixed(2)} {confidenceBadge}
      </span>
    </div>
  );
}
