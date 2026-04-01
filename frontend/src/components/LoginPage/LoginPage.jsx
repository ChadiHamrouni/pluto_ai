import { useState } from "react";
import "./LoginPage.css";

/**
 * LoginPage — full-screen login gate.
 *
 * Props:
 *  - onLogin(username, password) => Promise  — called on form submit
 *  - loading  bool
 *  - error    string | null
 */
export default function LoginPage({ onLogin, loading, error }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!username || !password || loading) return;
    onLogin(username, password);
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-logo">
          <span className="login-logo-dot" />
          <span className="login-logo-name">Pluto</span>
        </div>

        <p className="login-tagline">Your personal AI assistant</p>

        <form className="login-form" onSubmit={handleSubmit} autoComplete="on">
          <div className="login-field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="username"
              disabled={loading}
              autoFocus
            />
          </div>

          <div className="login-field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              disabled={loading}
            />
          </div>

          {error && <p className="login-error">{error}</p>}

          <button
            type="submit"
            className="login-btn"
            disabled={loading || !username || !password}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
