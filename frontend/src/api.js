const BASE = "http://localhost:8000";
let sessionId = null;

/** Switch the active session used by sendMessage. */
export function setActiveSession(id) {
  sessionId = id;
}

/** Create a new backend session and return its id. */
export async function createSession() {
  const r = await fetch(`${BASE}/chat/session`, { method: "POST" });
  if (!r.ok) throw new Error("Failed to create session");
  const d = await r.json();
  return d.session_id;
}

export async function sendMessage(message, files = []) {
  const formData = new FormData();
  formData.append("message", message);
  formData.append("session_id", sessionId);

  const fileList = Array.isArray(files) ? files : (files ? [files] : []);
  for (const f of fileList) {
    formData.append("attachments", f);
  }

  console.log("[api] POST /chat — message:", JSON.stringify(message).slice(0, 120), "| files:", fileList.length, "| session:", sessionId);
  const r = await fetch(`${BASE}/chat`, { method: "POST", body: formData });

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

    const r = await fetch(`${BASE}/chat/stream`, {
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

    callbacks.onDone?.({
      response: fileUrl ? "Your presentation is ready." : fullResponse,
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

export async function getModels() {
  const r = await fetch(`${BASE}/settings/models`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).models;
}

export async function fetchCommands() {
  const r = await fetch(`${BASE}/chat/commands`);
  if (!r.ok) return [];
  return r.json();
}

export async function getAgentSettings() {
  const r = await fetch(`${BASE}/settings/agents`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function saveAgentSettings(settings) {
  const r = await fetch(`${BASE}/settings/agents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function getSessions() {
  const r = await fetch(`${BASE}/chat/sessions`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).sessions;
}

export async function getSessionMessages(sessionId) {
  const r = await fetch(`${BASE}/chat/session/${sessionId}/messages`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return (await r.json()).messages;
}

export async function deleteSession(sessionId) {
  const r = await fetch(`${BASE}/chat/session/${sessionId}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
}

export async function fetchFile(fileUrl) {
  const r = await fetch(`${BASE}${fileUrl}`);
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.blob();
}

export async function startAutonomous(task) {
  const formData = new FormData();
  formData.append("task", task);
  if (sessionId) formData.append("session_id", sessionId);
  const r = await fetch(`${BASE}/autonomous/start`, { method: "POST", body: formData });
  if (!r.ok) throw new Error(`Error ${r.status}: ${await r.text()}`);
  return r.json();
}

export async function cancelAutonomous(taskId) {
  await fetch(`${BASE}/autonomous/${taskId}/cancel`, { method: "POST" });
}

export function streamAutonomous(taskId, onUpdate, onDone) {
  const es = new EventSource(`${BASE}/autonomous/${taskId}/stream`);
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

export async function ttsStream(text, signal) {
  const r = await fetch(`${BASE}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  return r;
}

export async function ttsStreamSentences(text, signal) {
  const r = await fetch(`${BASE}/tts/sentences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  return r;
}