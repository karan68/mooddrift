import { useState, useCallback, useEffect } from "react";
import VoiceCheckin from "./components/VoiceCheckin";
import InsightCard from "./components/InsightCard";
import EntryList from "./components/EntryList";
import Settings from "./components/Settings";
import TherapistReport from "./components/TherapistReport";
import TimeCapsulePanel from "./components/TimeCapsule";
import UserInsights from "./components/UserInsights";
import { USER_PROFILES, setCurrentUser, getCurrentUser, fetchCapsuleNotifications } from "./utils/api";
import type { TimeCapsule } from "./utils/api";
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
  const [capsuleNotifs, setCapsuleNotifs] = useState<TimeCapsule[]>([]);
  const [notifDismissed, setNotifDismissed] = useState(false);

  useEffect(() => {
    fetchCapsuleNotifications()
      .then((data) => { if (data.has_notifications) setCapsuleNotifs(data.capsules); })
      .catch(() => {});
  }, [activeUser, refreshKey]);

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

            {/* Capsule notification banner */}
            {capsuleNotifs.length > 0 && !notifDismissed && (
              <div style={{
                margin: "0 0 16px", padding: "14px 16px",
                background: "linear-gradient(135deg, rgba(139,92,246,0.15), rgba(236,72,153,0.12))",
                border: "1px solid rgba(139,92,246,0.4)", borderRadius: 12,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: "#5b21b6", marginBottom: 4 }}>
                      💌 You have a time capsule to open!
                    </div>
                    <div style={{ fontSize: 13, color: "#4a4540" }}>
                      You left yourself a message on {capsuleNotifs[0].date}:
                      <em style={{ marginLeft: 4, color: "#6b6560" }}>"{capsuleNotifs[0].transcript.slice(0, 80)}..."</em>
                    </div>
                  </div>
                  <button onClick={() => setNotifDismissed(true)} style={{
                    background: "transparent", border: "none", color: "#6b6560",
                    cursor: "pointer", fontSize: 16, padding: 4,
                  }}>✕</button>
                </div>
              </div>
            )}
            <VoiceCheckin assistantId={VAPI_ASSISTANT_ID} />
            <InsightCard />
            <TimeCapsulePanel />
          </div>
        )}

        {tab === "journal" && (
          <div className="tab-content" key={`journal-${refreshKey}`}>
            <EntryList />
          </div>
        )}

        {tab === "insights" && (
          <div className="tab-content" key={`insights-${refreshKey}`}>
            <UserInsights />
          </div>
        )}

        {tab === "settings" && (
          <div className="tab-content">
            <TherapistReport />
            <div className="no-print">
              <Settings />
              <footer className="disclaimer">
                MoodDrift is an emotional self-awareness tool. It is <strong>not</strong> a medical device,
                diagnostic tool, or substitute for professional mental health care.
                If you are in crisis, contact iCall at 9152987821 or Vandrevala Foundation at 1860-2662-345.
              </footer>
            </div>
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
