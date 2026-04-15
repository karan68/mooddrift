import { useState } from "react";
import { fetchReport, getCurrentUser, USER_PROFILES } from "../utils/api";

interface ReportData {
  user_id: string;
  period_days: number;
  generated_at: string;
  summary: {
    total_entries: number;
    avg_sentiment: number;
    min_sentiment: number;
    max_sentiment: number;
    days_with_entries: number;
  };
  sentiment_trend: { date: string; avg_sentiment: number; entries: number }[];
  top_keywords: { word: string; count: number }[];
  key_entries: {
    most_negative: { date: string; transcript: string; sentiment: number }[];
    most_positive: { date: string; transcript: string; sentiment: number }[];
  };
  drift: {
    detected: boolean;
    severity: string;
    message: string;
    matching_period: string | null;
  };
  coping_strategies: { date: string; strategy: string }[];
}

function sentimentLabel(s: number): string {
  if (s > 0.3) return "Positive";
  if (s > 0) return "Slightly positive";
  if (s > -0.3) return "Neutral / Mixed";
  return "Negative";
}

function sentimentDot(s: number): string {
  if (s > 0.3) return "🟢";
  if (s > 0) return "🟡";
  if (s > -0.3) return "🟠";
  return "🔴";
}

export default function TherapistReport() {
  const [report, setReport] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(14);

  const generate = async () => {
    setLoading(true);
    try {
      const data = await fetchReport(days);
      setReport(data);
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const profile = USER_PROFILES[getCurrentUser()];

  if (!report) {
    return (
      <div className="report-trigger">
        <h2>Therapist Report</h2>
        <p className="report-desc">
          Generate a summary to share with your therapist or counselor.
          No session time wasted on catching up.
        </p>
        <div className="report-options">
          <select
            className="setting-select"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 2 weeks</option>
            <option value={30}>Last 30 days</option>
          </select>
          <button className="report-btn" onClick={generate} disabled={loading}>
            {loading ? "Generating…" : "Generate report"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="report-container">
      {/* Print / back controls — hidden in print */}
      <div className="report-actions no-print">
        <button className="report-btn-secondary" onClick={() => setReport(null)}>
          ← Back
        </button>
        <button className="report-btn" onClick={handlePrint}>
          Print / Save PDF
        </button>
      </div>

      {/* === Printable report === */}
      <div className="report" id="therapist-report">
        <header className="report-header">
          <div>
            <h1>MoodDrift — Emotional Health Summary</h1>
            <p>
              {profile?.label || report.user_id} · Last {report.period_days} days · Generated {report.generated_at}
            </p>
          </div>
          <p className="report-disclaimer">
            For clinical discussion only. Not a diagnosis.
          </p>
        </header>

        {/* Overview */}
        <section className="report-section">
          <h2>Overview</h2>
          <div className="report-stats">
            <div className="report-stat">
              <span className="report-stat-value">{report.summary.total_entries}</span>
              <span className="report-stat-label">Entries</span>
            </div>
            <div className="report-stat">
              <span className="report-stat-value">{report.summary.days_with_entries}</span>
              <span className="report-stat-label">Active days</span>
            </div>
            <div className="report-stat">
              <span className="report-stat-value">{sentimentLabel(report.summary.avg_sentiment)}</span>
              <span className="report-stat-label">Avg. mood ({report.summary.avg_sentiment.toFixed(2)})</span>
            </div>
            <div className="report-stat">
              <span className="report-stat-value">{report.drift.detected ? report.drift.severity : "Stable"}</span>
              <span className="report-stat-label">Drift status</span>
            </div>
          </div>
        </section>

        {/* Drift insight */}
        {report.drift.detected && (
          <section className="report-section">
            <h2>Pattern Alert</h2>
            <p>{report.drift.message}</p>
            {report.drift.matching_period && (
              <p className="report-meta">Similar to: {report.drift.matching_period}</p>
            )}
          </section>
        )}

        {/* Sentiment trend */}
        <section className="report-section">
          <h2>Daily Sentiment Trend</h2>
          <table className="report-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Mood</th>
                <th>Score</th>
                <th>Entries</th>
              </tr>
            </thead>
            <tbody>
              {report.sentiment_trend.map((d) => (
                <tr key={d.date}>
                  <td>{d.date}</td>
                  <td>{sentimentDot(d.avg_sentiment)}</td>
                  <td>{d.avg_sentiment.toFixed(2)}</td>
                  <td>{d.entries}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* Key themes */}
        <section className="report-section">
          <h2>Recurring Themes</h2>
          <div className="report-keywords">
            {report.top_keywords.map((kw) => (
              <span key={kw.word} className="report-keyword">
                {kw.word} <small>×{kw.count}</small>
              </span>
            ))}
          </div>
        </section>

        {/* Difficult moments */}
        <section className="report-section">
          <h2>Most Difficult Moments</h2>
          {report.key_entries.most_negative.map((e, i) => (
            <div key={i} className="report-entry report-entry--negative">
              <span className="report-entry-date">{e.date} ({e.sentiment.toFixed(2)})</span>
              <p>{e.transcript}</p>
            </div>
          ))}
        </section>

        {/* Positive moments */}
        <section className="report-section">
          <h2>Positive Moments</h2>
          {report.key_entries.most_positive.map((e, i) => (
            <div key={i} className="report-entry report-entry--positive">
              <span className="report-entry-date">{e.date} ({e.sentiment.toFixed(2)})</span>
              <p>{e.transcript}</p>
            </div>
          ))}
        </section>

        {/* Coping strategies */}
        {report.coping_strategies.length > 0 && (
          <section className="report-section">
            <h2>Coping Strategies Identified</h2>
            {report.coping_strategies.map((c, i) => (
              <div key={i} className="report-entry report-entry--coping">
                <span className="report-entry-date">{c.date}</span>
                <p>{c.strategy}</p>
              </div>
            ))}
          </section>
        )}

        <footer className="report-footer">
          <p>
            Generated by MoodDrift · Not a diagnostic tool ·
            Entries are the patient's own words via voice/text journaling
          </p>
        </footer>
      </div>
    </div>
  );
}
