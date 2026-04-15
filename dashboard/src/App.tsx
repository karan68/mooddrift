import { useState, useCallback } from "react";
import VoiceCheckin from "./components/VoiceCheckin";
import InsightCard from "./components/InsightCard";
import ScatterPlot from "./components/ScatterPlot";
import DriftTimeline from "./components/DriftTimeline";
import EntryList from "./components/EntryList";
import Settings from "./components/Settings";
import { USER_PROFILES, setCurrentUser, getCurrentUser } from "./utils/api";
import "./App.css";

// Set this after creating assistant via scripts/create_assistant.py
const VAPI_ASSISTANT_ID = import.meta.env.VITE_VAPI_ASSISTANT_ID || "";

function App() {
  const [showAnalytics, setShowAnalytics] = useState(false);
  const [activeUser, setActiveUser] = useState(getCurrentUser());
  const [refreshKey, setRefreshKey] = useState(0);

  const switchUser = useCallback((userId: string) => {
    setCurrentUser(userId);
    setActiveUser(userId);
    setRefreshKey((k) => k + 1); // force re-render all data hooks
  }, []);

  const profile = USER_PROFILES[activeUser];

  return (
    <div className="app">
      <header className="app-header">
        <h1>MoodDrift</h1>
        <p className="tagline">Your journal that listens, remembers, and notices what you don't.</p>
      </header>

      {/* === Profile Selector === */}
      <div className="profile-selector">
        {Object.entries(USER_PROFILES).map(([id, p]) => (
          <button
            key={id}
            className={`profile-btn ${id === activeUser ? "profile-btn--active" : ""}`}
            onClick={() => switchUser(id)}
          >
            <span className="profile-label">{p.label}</span>
            <span className="profile-desc">{p.description}</span>
          </button>
        ))}
      </div>

      {/* === Primary: Insight + Voice === */}
      <section className="hero-section" key={refreshKey}>
        <InsightCard />
        <VoiceCheckin assistantId={VAPI_ASSISTANT_ID} />
      </section>

      {/* === Recent entries === */}
      <section className="entries-section" key={`entries-${refreshKey}`}>
        <EntryList />
      </section>

      {/* === Analytics toggle === */}
      <button
        className="analytics-toggle"
        onClick={() => setShowAnalytics(!showAnalytics)}
      >
        {showAnalytics ? "Hide analytics" : "Show analytics & patterns"}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ transform: showAnalytics ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {showAnalytics && (
        <section className="analytics-section" key={`analytics-${refreshKey}`}>
          <ScatterPlot />
          <DriftTimeline />
        </section>
      )}

      {/* === Settings === */}
      <section className="settings-section">
        <Settings />
      </section>

      {/* === Disclaimer === */}
      <footer className="disclaimer">
        MoodDrift is an emotional self-awareness tool. It is <strong>not</strong> a medical device, diagnostic tool, or substitute for professional mental health care.
        {" "}If you are in crisis, contact iCall at 9152987821 or Vandrevala Foundation at 1860-2662-345.
      </footer>
    </div>
  );
}

export default App;
