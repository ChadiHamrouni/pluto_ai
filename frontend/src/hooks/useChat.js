/**
 * useChat — handles sending messages and autonomous mode.
 *
 * Responsibilities:
 *  - Normal chat: send message → append user bubble → call backend → append reply
 *  - Autonomous mode: start task → stream plan updates → append summary on done
 *  - Retry on "Failed to fetch" (backend temporarily unreachable)
 *  - Expose `thinking`, `error`, `currentPlan`, and `handleAutoCancel`
 */

import { useRef, useState } from "react";
import {
  sendMessage,
  startAutonomous,
  cancelAutonomous,
  streamAutonomous,
} from "../api";

export function useChat({ activeId, messages, appendMessage, updateSession }) {
  const [thinking, setThinking]     = useState(false);
  const [error, setError]           = useState(null);
  const [currentPlan, setCurrentPlan] = useState(null);

  const autoTaskIdRef = useRef(null);
  const autoEsRef     = useRef(null);

  // ── Cancel an in-progress autonomous task ────────────────────────────────

  async function handleAutoCancel() {
    if (autoTaskIdRef.current) {
      await cancelAutonomous(autoTaskIdRef.current);
      autoTaskIdRef.current = null;
    }
    autoEsRef.current?.close();
    autoEsRef.current = null;
    setThinking(false);
  }

  // ── Send ─────────────────────────────────────────────────────────────────

  async function handleSend({ text, attachments, autoMode, inputRef, setInput, setAttachments }) {
    if ((!text && !attachments.length) || thinking || !activeId) return;

    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setError(null);

    // Auto-title the session from its first message
    if (messages.length === 0 && text) {
      const title = text.length > 40 ? text.slice(0, 40) + "…" : text;
      updateSession(activeId, () => ({ title }));
    }

    // ── Autonomous mode ───────────────────────────────────────────────────
    if (autoMode && text) {
      setAttachments([]);
      appendMessage(activeId, { role: "user", content: `[AUTO] ${text}` });
      setThinking(true);
      setCurrentPlan(null);

      try {
        const { task_id } = await startAutonomous(text);
        autoTaskIdRef.current = task_id;

        const es = streamAutonomous(
          task_id,
          (event) => {
            if (event.plan) setCurrentPlan(event.plan);
          },
          (event) => {
            if (event?.plan) setCurrentPlan(event.plan);
            autoTaskIdRef.current = null;
            autoEsRef.current = null;
            setThinking(false);

            const failed  = event?.plan?.steps?.filter(s => s.status === "failed") ?? [];
            const summary = event?.plan?.status === "completed"
              ? `Autonomous task completed${failed.length ? ` (${failed.length} step(s) failed)` : ""}.`
              : "Autonomous task stopped.";

            appendMessage(activeId, { role: "assistant", content: summary });
            inputRef.current?.focus();
          }
        );
        autoEsRef.current = es;
      } catch (e) {
        setError(e.message);
        setThinking(false);
      }
      return;
    }

    // ── Normal chat ───────────────────────────────────────────────────────
    const sentAttachments = attachments;
    setAttachments([]);
    appendMessage(activeId, {
      role: "user",
      content: text || "(image)",
      previews: sentAttachments.map(a => a.preview),
    });
    setThinking(true);

    const currentSessionId = activeId;

    const tryFetch = async () => {
      try {
        const { response: reply, tools_used, agents_trace, file_url } =
          await sendMessage(
            text || "(describe this image)",
            sentAttachments.map(a => a.file)
          );
        appendMessage(currentSessionId, {
          role: "assistant",
          content: reply,
          tools_used,
          agents_trace,
          file_url,
        });
        setThinking(false);
        inputRef.current?.focus();
      } catch (e) {
        if (e.message === "Failed to fetch") {
          setTimeout(tryFetch, 3000);
        } else {
          setError(e.message);
          setThinking(false);
          inputRef.current?.focus();
        }
      }
    };

    tryFetch();
  }

  return {
    thinking,
    error,
    setError,
    currentPlan,
    setCurrentPlan,
    handleSend,
    handleAutoCancel,
  };
}
