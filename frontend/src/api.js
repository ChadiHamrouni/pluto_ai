const BASE = "http://localhost:8000";
let sessionId = null;

// ── Token storage (memory-only; persisted across page reloads via localStorage) ──

let _accessToken = localStorage.getItem("access_token") || null;
let _refreshToken = localStorage.getItem("refresh_token") || null;
let _refreshPromise = null; // deduplicate concurrent refresh calls

function _setTokens(access, refresh) {
  _accessToken = access;
  _refreshToken = refresh;
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

function _clearTokens() {
  _accessToken = null;
  _refreshToken = null;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}

export function hasToken() {
  return Boolean(_accessToken);
}

// ── Auth API ──────────────────────────────────────────────────────────────────

export async function login(username, password) {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail || `Login failed (${r.status})`);
  }
  const d = await r.json();
  _setTokens(d.access_token, d.refresh_token);
}

export function logout() {
  _clearTokens();
  sessionId = null;
}

async function _refresh() {
  if (!_refreshToken) throw new Error("No refresh token");
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: _refreshToken }),
  });
  if (!r.ok) {
    _clearTokens();
    throw new Error("Session expired — please log in again.");
  }
  const d = await r.json();
  _setTokens(d.access_token, d.refresh_token);
}

// ── Authenticated fetch wrapper ───────────────────────────────────────────────
// Injects Authorization + X-Requested-With, auto-refreshes on 401.

async function _fetch(url, options = {}, retry = true) {
  const headers = {
    ...(options.headers || {}),
    "Authorization": `Bearer ${_accessToken}`,
    "X-Requested-With": "XMLHttpRequest",
  };

  const r = await fetch(url, { ...options, headers });

  if (r.status === 401 && retry && _refreshToken) {
    // Deduplicate: if a refresh is already in-flight, wait for it
    if (!_refreshPromise) {
      _refreshPromise = _refresh().finally(() => { _refreshPromise = null; });
    }
    try {
      await _refreshPromise;
    } catch {
      throw new Error("Session expired — please log in again.");
    }
    return _fetch(url, options, false); // retry once
  }

  return r;
}

// ── Session ───────────────────────────────────────────────────────────────────

export function setActiveSession(id) {
  sessionId = id;
}

export async function createSession() {
  const r = await _fetch(`${BASE}/chat/session`, { method: "POST" });
  if (!r.ok) throw new Error("Failed to create session");
  const d = await r.json();
  return d.session_id;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export async function sendMessage(message, files = []) {
  const formData = new FormData();
  formData.append("message", message);
  formData.append("session_id", sessionId);

  const fileList = Array.isArray(files) ? files : (files ? [files] : []);
  for (const f of fileList) {
    formData.append("attachments", f);
  }

  console.log("[api] POST /chat — message:", JSON.stringify(message).slice(0, 120), "| files:", fileList.length, "| session:", sessionId);
  const r = await _fetch(`${BASE}/chat`, { method: "POST", body: formData });

  if (!r.ok) {
    const body = await r.text();
    console.error("[api] /chat error:", r.status, body);
    throw new Error(`Error ${r.status}: ${body}`);
  }
  const d = await r.json();
  console.log("[api] /chat response received, length:", d.response?.length ?? 0);
  return { response: d.response, tools_used: d.tools_used ?? [], agents_trace: d.agents_trace ?? [], file_url: d.file_url ?? null };
}

/**
 * Stream a chat response via SSE (POST /chat/stream).
 *
 * @param {string} message
 * @param {object} callbacks — { onToken, onToolCall, onHandoff, onDone, onError }
 * @returns {AbortController} — call .abort() to cancel the stream
 */
export function streamMessage(message, callbacks = {}) {
  const controller = new AbortController();

  (async () => {
    const formData = new FormData();
    formData.append("message", message);
    formData.append("session_id", sessionId);

    const r = await _fetch(`${BASE}/chat/stream`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });

    if (!r.ok) {
      const body = await r.text();
      callbacks.onError?.(body);
      return;
    }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullResponse = "";
    let toolsUsed = [];
    let agentsTrace = [];
    let fileUrl = null;
    let tokenCount = 0;
    let streamStart = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop();

      let eventType = null;
      let dataLines = [];

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLines.push(line.slice(6));
        } else if (line === "" && eventType) {
          const raw = dataLines.join("\n");
          try {
            const data = JSON.parse(raw);
            switch (eventType) {
              case "token": {
                const delta = data.delta || "";
                if (delta) {
                  if (streamStart === null) streamStart = performance.now();
                  tokenCount += delta.split(/\s+/).filter(Boolean).length;
                  fullResponse += delta;
                  callbacks.onToken?.(delta);
                }
                break;
              }
              case "tool_call":
                callbacks.onToolCall?.(data);
                break;
              case "agent_handoff":
                callbacks.onHandoff?.(data);
                break;
              case "file_url":
                fileUrl = data.file_url;
                break;
              case "done":
                fullResponse = data.response || fullResponse;
                toolsUsed = data.tools_used || [];
                agentsTrace = data.agents_trace || [];
                break;
              case "error":
                callbacks.onError?.(data.message);
                break;
            }
          } catch {}
          eventType = null;
          dataLines = [];
        }
      }
    }

    const elapsedSec = streamStart !== null ? (performance.now() - streamStart) / 1000 : null;
    const tokensPerSecond = elapsedSec && tokenCount > 0
      ? Math.round(tokenCount / elapsedSec)
      : null;

    let finalResponse = fullResponse;
    if (fileUrl) {
      finalResponse = fileUrl.endsWith(".png") ? "Your diagram is ready." : "Your presentation is ready.";
    }

    callbacks.onDone?.({
      response: finalResponse,
      tools_used: toolsUsed,
      agents_trace: agentsTrace,
      file_url: fileUrl,
      tokens_per_second: tokensPerSecond,
    });
  })().catch((err) => {
    if (err.name !== "AbortError") {
      callbacks.onError?.(err.message);
    }
  });

  return controller;
}

// ── Settings ──────────────────────────────────────────────────────────────────

export async function getModels() {
  const r = await _fetch(`${BASE}/settings/models`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).models;
}

export async function fetchCommands() {
  const r = await _fetch(`${BASE}/chat/commands`);
  if (!r.ok) return [];
  return r.json();
}

export async function getAgentSettings() {
  const r = await _fetch(`${BASE}/settings/agents`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function saveAgentSettings(settings) {
  const r = await _fetch(`${BASE}/settings/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── Vault ────────────────────────────────────────────────────────────────────

export async function getVaultPath() {
  const r = await _fetch(`${BASE}/settings/vault`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).vault_path;
}

export async function setVaultPath(vaultPath) {
  const r = await _fetch(`${BASE}/settings/vault`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vault_path: vaultPath }),
  });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export async function getSessions() {
  const r = await _fetch(`${BASE}/chat/sessions`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).sessions;
}

export async function getSessionMessages(id) {
  const r = await _fetch(`${BASE}/chat/session/${id}/messages`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).messages;
}

export async function deleteSession(id) {
  const r = await _fetch(`${BASE}/chat/session/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
}

// ── File serving ──────────────────────────────────────────────────────────────

export async function fetchFile(fileUrl) {
  const r = await _fetch(`${BASE}${fileUrl}`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.blob();
}

// ── Content search ────────────────────────────────────────────────────────────

export async function searchContent(query, topK = 10) {
  const params = new URLSearchParams({ q: query, top_k: topK });
  const r = await _fetch(`${BASE}/search?${params}`);
  if (!r.ok) throw new Error(`Search error ${r.status}: ${await r.text()}`);
  return r.json();
}

// ── Autonomous ────────────────────────────────────────────────────────────────

export async function startAutonomous(task) {
  const formData = new FormData();
  formData.append("task", task);
  if (sessionId) formData.append("session_id", sessionId);
  const r = await _fetch(`${BASE}/autonomous/start`, { method: "POST", body: formData });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function cancelAutonomous(taskId) {
  await _fetch(`${BASE}/autonomous/${taskId}/cancel`, { method: "POST" });
}

// Autonomous SSE — EventSource can't send headers, so we use fetch+ReadableStream
export function streamAutonomous(taskId, onUpdate, onDone) {
  const controller = new AbortController();

  (async () => {
    const r = await _fetch(`${BASE}/autonomous/${taskId}/stream`, {
      signal: controller.signal,
    });
    if (!r.ok) { onDone(null); return; }

    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let eventType = null;
    let dataLines = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataLines.push(line.slice(6));
        } else if (line === "" && eventType) {
          const raw = dataLines.join("\n");
          try {
            const data = JSON.parse(raw);
            if (eventType === "done") {
              onDone(data);
            } else if (eventType === "update") {
              onUpdate(data);
            }
          } catch {}
          eventType = null;
          dataLines = [];
        }
      }
    }
  })().catch((err) => {
    if (err.name !== "AbortError") onDone(null);
  });

  return { close: () => controller.abort() };
}

// ── TTS ───────────────────────────────────────────────────────────────────────

export async function ttsStream(text, signal) {
  return _fetch(`${BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
}

export async function ttsStreamSentences(text, signal) {
  return _fetch(`${BASE}/tts/sentences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
}
