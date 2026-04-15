import { useState } from "react";

export default function Settings() {
  const [channel, setChannel] = useState("telegram");
  const [time, setTime] = useState("20:00");
  const [weeklySummary, setWeeklySummary] = useState(true);
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="panel settings-panel">
      <h2>Check-in Settings</h2>

      {/* Reminder Channel */}
      <div className="setting-group">
        <label className="setting-label">Reminder channel</label>
        <div className="channel-options">
          <button
            className={`channel-btn ${channel === "telegram" ? "channel-btn--active" : ""}`}
            onClick={() => setChannel("telegram")}
          >
            <span className="channel-icon">✈️</span>
            <span className="channel-name">Telegram</span>
            <span className="channel-status channel-status--live">Active</span>
          </button>
          <button
            className={`channel-btn ${channel === "whatsapp" ? "channel-btn--active" : ""}`}
            onClick={() => setChannel("whatsapp")}
            disabled
          >
            <span className="channel-icon">💬</span>
            <span className="channel-name">WhatsApp</span>
            <span className="channel-status channel-status--soon">Coming soon</span>
          </button>
        </div>
      </div>

      {/* Reminder Time */}
      <div className="setting-group">
        <label className="setting-label">Daily check-in time</label>
        <select
          className="setting-select"
          value={time}
          onChange={(e) => setTime(e.target.value)}
        >
          <option value="08:00">Morning — 8:00 AM</option>
          <option value="14:00">Afternoon — 2:00 PM</option>
          <option value="20:00">Evening — 8:00 PM</option>
          <option value="22:00">Night — 10:00 PM</option>
        </select>
        <p className="setting-hint">
          You'll receive a gentle nudge at this time if you haven't checked in today.
        </p>
      </div>

      {/* Weekly Summary */}
      <div className="setting-group">
        <label className="setting-label">
          <input
            type="checkbox"
            checked={weeklySummary}
            onChange={(e) => setWeeklySummary(e.target.checked)}
            className="setting-checkbox"
          />
          Weekly voice summary
        </label>
        <p className="setting-hint">
          Every Sunday, receive a voice note summarizing your week — mood trends, recurring themes, and any drift detected.
        </p>
      </div>

      {/* Save */}
      <button className="setting-save" onClick={handleSave}>
        {saved ? "✓ Saved" : "Save preferences"}
      </button>

      {/* Next reminder preview */}
      <div className="reminder-preview">
        <div className="reminder-preview-icon">🔔</div>
        <div className="reminder-preview-text">
          <strong>Next check-in reminder</strong>
          <span>
            Today at {time === "08:00" ? "8:00 PM" : time === "14:00" ? "2:00 PM" : time === "20:00" ? "8:00 PM" : "10:00 PM"} via{" "}
            {channel === "telegram" ? "Telegram" : "WhatsApp"}
          </span>
        </div>
      </div>

      {/* Telegram connect */}
      {channel === "telegram" && (
        <div className="telegram-connect">
          <p>
            <strong>Connect your Telegram:</strong> Search for <code>@MoodDriftBot</code> on Telegram and send <code>/start</code> to begin receiving check-in reminders and voice summaries.
          </p>
        </div>
      )}
    </div>
  );
}
