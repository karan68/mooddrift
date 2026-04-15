import { useState, useCallback } from "react";
import VoiceCheckin from "./components/VoiceCheckin";
import InsightCard from "./components/InsightCard";
import ScatterPlot from "./components/ScatterPlot";
import DriftTimeline from "./components/DriftTimeline";
import EntryList from "./components/EntryList";
import Settings from "./components/Settings";
import TherapistReport from "./components/TherapistReport";
import { USER_PROFILES, setCurrentUser, getCurrentUser } from "./utils/api";
import "./App.css";

const VAPI_ASSISTANT_ID = import.meta.env.VITE_VAPI_ASSISTANT_ID || "";

type Tab = "today" | "journal" | "insights" | "settings";

const TAB_ICONS: Record<Tab, string> = {
  today: "◉",
  journal: "☰",
  insights: "◈",
  settings: "⚙",
};

function App() {
  const [tab, setTab] = useState<Tab>("today");
  const [activeUser, setActiveUser] = useState(getCurrentUser());
  const [refreshKey, setRefreshKey] = useState(0);

  const switchUser = useCallback((userId: string) => {
    setCurrentUser(userId);
    setActiveUser(userId);
    setRefreshKey((k) => k + 1);
  }, []);

  return (
    <div className="app">
      {/* === Top bar === */}
      <header className="topbar">
        <div className="topbar-brand">
          <h1>MoodDrift</h1>
        </div>
        <div className="topbar-profiles">
          {Object.entries(USER_PROFILES).map(([id, p]) => (
            <div key={id} className="profile-wrap">
              <button
                className={`profile-pill ${id === activeUser ? "profile-pill--active" : ""}`}
                onClick={() => switchUser(id)}
              >
                {p.label.split(" ")[0]}
              </button>
              <div className="profile-tooltip">
                <strong>{p.label}</strong>
                <span>{p.tooltip}</span>
              </div>
            </div>
          ))}
        </div>
      </header>

      {/* === Content area === */}
      <main className="content">
        {tab === "today" && (
          <div className="tab-content" key={`today-${refreshKey}`}>
            <div className="greeting">
              <h2>How are you today?</h2>
              <p className="greeting-sub">Check in with yourself. It takes less than a minute.</p>
            </div>
            <VoiceCheckin assistantId={VAPI_ASSISTANT_ID} />
            <InsightCard />
          </div>
        )}

        {tab === "journal" && (
          <div className="tab-content" key={`journal-${refreshKey}`}>
            <EntryList />
          </div>
        )}

        {tab === "insights" && (
          <div className="tab-content" key={`insights-${refreshKey}`}>
            <div className="insights-grid">
              <DriftTimeline />
              <ScatterPlot />
            </div>
          </div>
        )}

        {tab === "settings" && (
          <div className="tab-content">
            <TherapistReport />
            <Settings />
            <footer className="disclaimer">
              MoodDrift is an emotional self-awareness tool. It is <strong>not</strong> a medical device,
              diagnostic tool, or substitute for professional mental health care.
              If you are in crisis, contact iCall at 9152987821 or Vandrevala Foundation at 1860-2662-345.
            </footer>
          </div>
        )}
      </main>

      {/* === Bottom nav === */}
      <nav className="bottomnav">
        {(["today", "journal", "insights", "settings"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`nav-btn ${tab === t ? "nav-btn--active" : ""}`}
            onClick={() => setTab(t)}
          >
            <span className="nav-icon">{TAB_ICONS[t]}</span>
            <span className="nav-label">{t.charAt(0).toUpperCase() + t.slice(1)}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}

export default App;
