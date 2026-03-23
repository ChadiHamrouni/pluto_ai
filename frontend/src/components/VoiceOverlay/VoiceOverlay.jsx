import { useState, useEffect } from "react";
import "./VoiceOverlay.css";

const STATE_WORDS = {
  idle:       ["Listening…", "Ready", "Waiting…"],
  recording:  ["Hearing you…", "Listening…", "Go ahead…"],
  thinking:   ["Thinking…", "Processing…", "One moment…"],
  speaking:   ["Speaking…", "Responding…", "Playing…"],
};

export default function VoiceOverlay({ recording, transcribing, thinking, speaking, lastTranscript, onExit }) {
  const state = speaking     ? "speaking"
              : recording    ? "recording"
              : transcribing ? "thinking"
              : thinking     ? "thinking"
              : "idle";

  const [stars, setStars] = useState([]);
  const [wordIndex, setWordIndex] = useState(0);
  const [phase, setPhase] = useState("in");

  // Stars burst — faster when active, slow when idle
  useEffect(() => {
    const interval = state === "idle" ? 600 : 280;
    const loop = setInterval(() => {
      const id  = Math.random();
      const star = {
        id,
        x:     30 + Math.random() * 80,   // spread around center
        y:     30 + Math.random() * 80,
        size:  8 + Math.random() * 10,
        delay: Math.random() * 0.3,
      };
      setStars((prev) => [...prev.slice(-8), star]);
      setTimeout(() => setStars((prev) => prev.filter((s) => s.id !== id)), 900);
    }, interval);
    return () => clearInterval(loop);
  }, [state]);

  // Rotate words for current state
  const words = STATE_WORDS[state];
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
  }, [state]);

  return (
    <div className="voice-overlay">
      {/* Stars cluster */}
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

      {/* State label */}
      <p className={`voice-overlay-label status-${phase}`}>{words[wordIndex]}</p>

      {/* Last transcribed text */}
      {lastTranscript && (
        <p className="voice-transcript">"{lastTranscript}"</p>
      )}

      {/* Exit — minimal, text only */}
      <button className="voice-exit" onClick={onExit}>
        exit voice
      </button>
    </div>
  );
}
