import { useState, useEffect } from "react";
import "./VoiceOverlay.css";

const STATE_WORDS = {
  idle:       ["Tap Voice to record", "Ready", "Tap to speak"],
  recording:  ["Hearing you…", "Listening…", "Go ahead…"],
  thinking:   ["Transcribing…", "Processing…", "One moment…"],
  speaking:   ["Speaking…", "Responding…", "Playing…"],
};

export default function VoiceOverlay({
  recording,
  transcribing,
  thinking,
  speaking,
  lastTranscript,
  waveformBars,
  onStop,
  onExit,
}) {
  const state = speaking     ? "speaking"
              : recording    ? "recording"
              : transcribing ? "thinking"
              : thinking     ? "thinking"
              : "idle";

  // Stars burst for non-recording states
  const [stars, setStars] = useState([]);
  useEffect(() => {
    const interval = (recording || speaking) ? 260 : 700;
    const loop = setInterval(() => {
      const id = Math.random();
      setStars((prev) => [...prev.slice(-8), {
        id,
        x:     30 + Math.random() * 80,
        y:     30 + Math.random() * 80,
        size:  8 + Math.random() * 10,
        delay: Math.random() * 0.3,
      }]);
      setTimeout(() => setStars((prev) => prev.filter((s) => s.id !== id)), 900);
    }, interval);
    return () => clearInterval(loop);
  }, [recording, speaking]);

  // Rotate state label words
  const words = STATE_WORDS[state];
  const [wordIndex, setWordIndex] = useState(0);
  const [phase, setPhase]         = useState("in");
  useEffect(() => {
    setWordIndex(0);
    setPhase("in");
    let t1, t2;
    const cycle = setInterval(() => {
      setPhase("out");
      t1 = setTimeout(() => {
        setWordIndex((i) => (i + 1) % words.length);
        setPhase("in");
        t2 = setTimeout(() => setPhase("hold"), 500);
      }, 500);
    }, 3000);
    setTimeout(() => setPhase("hold"), 500);
    return () => { clearInterval(cycle); clearTimeout(t1); clearTimeout(t2); };
  }, [state]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="voice-overlay">

      {/* ── Visualiser: waveform while recording, stars otherwise ── */}
      <div className="voice-visual">
        {recording ? (
          <div className="voice-waveform">
            {waveformBars.map((h, i) => (
              <div
                key={i}
                className="voice-waveform-bar"
                style={{ "--bar-h": Math.max(0.06, h) }}
              />
            ))}
          </div>
        ) : (
          <div className="voice-stars-wrap">
            <div className="voice-stars-field">
              {stars.map((s) => (
                <svg
                  key={s.id}
                  className="voice-star"
                  style={{ left: s.x, top: s.y, width: s.size, height: s.size, animationDelay: `${s.delay}s` }}
                  viewBox="0 0 24 24"
                >
                  <polygon
                    points="12,2 14.5,9.5 22,9.5 16,14.5 18.5,22 12,17.5 5.5,22 8,14.5 2,9.5 9.5,9.5"
                    fill="var(--neon)"
                  />
                </svg>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── State label ── */}
      <p className={`voice-overlay-label status-${phase}`}>{words[wordIndex]}</p>

      {/* ── Stop button (only while recording) ── */}
      {recording && (
        <button className="voice-stop-btn" onClick={onStop}>
          <span className="voice-stop-icon" />
          Stop
        </button>
      )}

      {/* ── Last transcript echo ── */}
      {!recording && lastTranscript && (
        <p className="voice-transcript">"{lastTranscript}"</p>
      )}

      <button className="voice-exit" onClick={onExit}>exit voice</button>
    </div>
  );
}
