const BASE = "http://localhost:8000";
let accessToken = null;
let refreshToken = null;
let sessionId = null;

/** Switch the active session used by sendMessage. */
export function setActiveSession(id) {
  sessionId = id;
}

/** Create a new backend session and return its id. */
export async function createSession() {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/chat/session`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!r.ok) throw new Error("Failed to create session");
  const d = await r.json();
  return d.session_id;
}

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

async function _doChat(formData) {
  return fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });
}

export async function sendMessage(message, files = []) {
  if (!accessToken) await login();

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
    r = await _doChat(formData);
  }

  if (!r.ok) {
    const body = await r.text();
    console.error("[api] /chat error:", r.status, body);
    throw new Error(`Error ${r.status}: ${body}`);
  }
  const d = await r.json();
  console.log("[api] /chat response received, length:", d.response?.length ?? 0);
  return { response: d.response, tools_used: d.tools_used ?? [], agents_trace: d.agents_trace ?? [], file_url: d.file_url ?? null };
}

export async function getModels() {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/settings/models`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (r.status === 401) { await refresh(); return getModels(); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).models;
}

export async function getAgentSettings() {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/settings/agents`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (r.status === 401) { await refresh(); return getAgentSettings(); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function saveAgentSettings(settings) {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/settings/agents`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(settings),
  });
  if (r.status === 401) { await refresh(); return saveAgentSettings(settings); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function getSessions() {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/chat/sessions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (r.status === 401) { await refresh(); return getSessions(); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).sessions; // [{id, title, created_at}]
}

export async function getSessionMessages(sessionId) {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/chat/session/${sessionId}/messages`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (r.status === 401) { await refresh(); return getSessionMessages(sessionId); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).messages; // [{role, content}]
}

export async function deleteSession(sessionId) {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}/chat/session/${sessionId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (r.status === 401) { await refresh(); return deleteSession(sessionId); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
}

export async function fetchFile(fileUrl) {
  if (!accessToken) await login();
  const r = await fetch(`${BASE}${fileUrl}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (r.status === 401) { await refresh(); return fetchFile(fileUrl); }
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.blob();
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
