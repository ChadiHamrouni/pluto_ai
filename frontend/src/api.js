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

async function _doChat(formData) {
  return fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });
}

export async function sendMessage(message, history, imageFile = null) {
  if (!accessToken) await login();

  const formData = new FormData();
  formData.append("message", message);
  formData.append("history", JSON.stringify(history));
  if (imageFile) formData.append("image", imageFile);

  let r = await _doChat(formData);

  if (r.status === 401) {
    await refresh();
    r = await _doChat(formData);
  }

  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  const d = await r.json();
  return d.response;
}