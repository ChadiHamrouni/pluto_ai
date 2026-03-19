const BASE = "http://localhost:8000";
let accessToken = null;
let refreshToken = null;
let sessionId = null;

async function login() {
  console.log("[api] logging in…");
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "changeme" }),
  });
  if (!r.ok) {
    console.error("[api] login failed:", r.status, await r.text());
    throw new Error("Login failed");
  }
  const d = await r.json();
  accessToken = d.access_token;
  refreshToken = d.refresh_token;
  console.log("[api] login OK");
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

async function ensureSession() {
  if (sessionId) return;
  console.log("[api] creating session…");
  const r = await fetch(`${BASE}/chat/session`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!r.ok) {
    console.error("[api] session creation failed:", r.status, await r.text());
    throw new Error("Failed to create session");
  }
  const d = await r.json();
  sessionId = d.session_id;
  console.log("[api] session created:", sessionId);
}

async function _doChat(formData) {
  return fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });
}

export async function sendMessage(message, files = []) {
  if (!accessToken) await login();
  await ensureSession();

  const formData = new FormData();
  formData.append("message", message);
  formData.append("session_id", sessionId);

  const fileList = Array.isArray(files) ? files : (files ? [files] : []);
  for (const f of fileList) {
    formData.append("attachments", f);
  }

  console.log("[api] POST /chat — message:", JSON.stringify(message).slice(0, 120), "| files:", fileList.length, "| session:", sessionId);
  let r = await _doChat(formData);

  if (r.status === 401) {
    console.warn("[api] 401 — refreshing token and retrying");
    await refresh();
    await ensureSession();
    formData.set("session_id", sessionId);
    r = await _doChat(formData);
  }

  if (!r.ok) {
    const body = await r.text();
    console.error("[api] /chat error:", r.status, body);
    throw new Error(`Error ${r.status}: ${body}`);
  }
  const d = await r.json();
  console.log("[api] /chat response received, length:", d.response?.length ?? 0);
  return d.response;
}

export async function startAutonomous(task) {
  if (!accessToken) await login();
  const formData = new FormData();
  formData.append("task", task);
  let r = await fetch(`${BASE}/autonomous/start`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });
  if (r.status === 401) {
    await refresh();
    r = await fetch(`${BASE}/autonomous/start`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      body: formData,
    });
  }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function cancelAutonomous(taskId) {
  if (!accessToken) await login();
  await fetch(`${BASE}/autonomous/${taskId}/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function streamAutonomous(taskId, onUpdate, onDone) {
  const es = new EventSource(
    `${BASE}/autonomous/${taskId}/stream?token=${accessToken}`
  );
  es.addEventListener("update", (e) => {
    try { onUpdate(JSON.parse(e.data)); } catch {}
  });
  es.addEventListener("done", (e) => {
    try { onDone(JSON.parse(e.data)); } catch {}
    es.close();
  });
  es.addEventListener("ping", () => {});
  es.onerror = () => { es.close(); onDone(null); };
  return es;
}
