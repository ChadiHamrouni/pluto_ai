import { useState, useEffect } from "react";
import { getModels, getAgentSettings, saveAgentSettings } from "../api";

const AGENTS = [
  { key: "orchestrator", label: "Main agent" },
  { key: "notes_agent",  label: "Notes agent" },
  { key: "slides_agent", label: "Slides agent" },
  { key: "autonomous",   label: "Autonomous agent" },
];

export default function SettingsPanel({ onClose }) {
  const [models, setModels]       = useState([]);
  const [values, setValues]       = useState({});
  const [status, setStatus]       = useState("loading"); // loading | ready | saving | saved | error
  const [errorMsg, setErrorMsg]   = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [m, s] = await Promise.all([getModels(), getAgentSettings()]);
        setModels(m);
        setValues(s);
        setStatus("ready");
      } catch (e) {
        setErrorMsg(e.message);
        setStatus("error");
      }
    }
    load();
  }, []);

  async function handleSave() {
    setStatus("saving");
    try {
      await saveAgentSettings(values);
      setStatus("saved");
      setTimeout(() => setStatus("ready"), 1500);
    } catch (e) {
      setErrorMsg(e.message);
      setStatus("error");
    }
  }

  function handleChange(key, val) {
    setValues((prev) => ({ ...prev, [key]: val }));
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <span className="settings-title">MODEL SETTINGS</span>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        {status === "loading" && (
          <p className="settings-hint">Loading models from Ollama…</p>
        )}

        {status === "error" && (
          <p className="settings-error">{errorMsg}</p>
        )}

        {(status === "ready" || status === "saving" || status === "saved") && (
          <>
            <p className="settings-hint">
              Showing models already pulled in your local Ollama.
            </p>

            <div className="settings-rows">
              {AGENTS.map(({ key, label }) => (
                <div key={key} className="settings-row">
                  <label className="settings-label">{label}</label>
                  <div className="settings-select-wrap">
                    <select
                      className="settings-select"
                      value={values[key] || ""}
                      onChange={(e) => handleChange(key, e.target.value)}
                      disabled={status === "saving"}
                    >
                      {values[key] && !models.includes(values[key]) && (
                        <option value={values[key]}>{values[key]}</option>
                      )}
                      {models.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <span className="settings-select-arrow">▾</span>
                  </div>
                </div>
              ))}
            </div>

            <button
              className={`settings-save ${status === "saved" ? "settings-save--done" : ""}`}
              onClick={handleSave}
              disabled={status === "saving"}
            >
              {status === "saving" ? "Saving…" : status === "saved" ? "Saved ✓" : "Save"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
