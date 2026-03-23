import { useState, useEffect } from "react";
import "./StatusLabel.css";

export default function StatusLabel({ words }) {
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState("in");
  const [stars, setStars] = useState([]);

  useEffect(() => {
    const loop = setInterval(() => {
      const id    = Math.random();
      const star  = {
        id,
        x:     Math.random() * 14,
        y:     Math.random() * 14,
        size:  7 + Math.random() * 7,
        delay: Math.random() * 0.4,
      };
      setStars((prev) => [...prev.slice(-5), star]);
      setTimeout(() => setStars((prev) => prev.filter((s) => s.id !== id)), 900);
    }, 350);
    return () => clearInterval(loop);
  }, []);

  useEffect(() => {
    let t1, t2;
    const cycle = setInterval(() => {
      setPhase("out");
      t1 = setTimeout(() => {
        setIndex((i) => (i + 1) % words.length);
        setPhase("in");
        t2 = setTimeout(() => setPhase("hold"), 500);
      }, 500);
    }, 4000);
    setTimeout(() => setPhase("hold"), 500);
    return () => { clearInterval(cycle); clearTimeout(t1); clearTimeout(t2); };
  }, [words]);

  return (
    <span className="status-container">
      <span className={`status-word status-${phase}`}>{words[index]}</span>
      <span className="status-stars" aria-hidden="true">
        {stars.map((s) => (
          <svg
            key={s.id}
            className="status-star"
            style={{ left: s.x, top: s.y, width: s.size, height: s.size, animationDelay: `${s.delay}s` }}
            viewBox="0 0 24 24"
          >
            <polygon
              points="12,2 14.5,9.5 22,9.5 16,14.5 18.5,22 12,17.5 5.5,22 8,14.5 2,9.5 9.5,9.5"
              fill="var(--neon)"
            />
          </svg>
        ))}
      </span>
    </span>
  );
}
