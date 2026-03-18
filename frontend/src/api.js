const BASE = "http://localhost:8000";
let accessToken = null;
let refreshToken = null;

async function login() {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "changeme" }),
  });
  if (!r.ok) throw new Error("Login failed");
  const d = await r.json();
  accessToken = d.access_token;
  refreshToken = d.refresh_token;
}

async function refresh() {
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!r.ok) throw new Error("Refresh failed");
  const d = await r.json();
  accessToken = d.access_token;
  refreshToken = d.refresh_token;
}

export async function sendMessage(message, history) {
  if (!accessToken) await login();

  const payload = { message, history };
  let r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(payload),
  });

  if (r.status === 401) {
    await refresh();
    r = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload),
    });
  }

  if (!r.ok) throw new Error(`Chat error: ${r.status}`);
  const d = await r.json();
  return d.response;
}