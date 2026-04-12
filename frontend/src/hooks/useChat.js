/**
 * useChat — handles sending messages via normal chat or streaming.
 */

import { useRef, useState } from "react";
import { sendMessage, streamMessage } from "../api";

export function useChat({ activeId, messages, appendMessage, appendDelta, finalizeLastMessage, updateSession, onReply }) {
  const [thinkingMap, setThinkingMap] = useState({});
  const [error, setError]             = useState(null);

  const thinking = thinkingMap[activeId] ?? false;

  const streamAbortRef = useRef(null);

  function setThinkingFor(sessionId, val) {
    setThinkingMap(prev => ({ ...prev, [sessionId]: val }));
  }

  async function handleEscape() {
    if (!thinking) return;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setThinkingFor(activeId, false);
  }

  async function handleSend({ text, attachments, inputRef, setInput, setAttachments }) {
    if ((!text && !attachments.length) || thinking || !activeId) return;

    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setError(null);

    if (messages.length === 0 && text) {
      const title = text.length > 40 ? text.slice(0, 40) + "…" : text;
      updateSession(activeId, () => ({ title }));
    }

    const sentAttachments = attachments;
    setAttachments([]);
    appendMessage(activeId, {
      role: "user",
      content: text || "(image)",
      previews: sentAttachments.map(a => a.preview).filter(Boolean),
      attachmentNames: sentAttachments.filter(a => !a.preview).map(a => a.file.name),
    });

    const currentSessionId = activeId;
    setThinkingFor(currentSessionId, true);

    const hasFiles = sentAttachments.length > 0;

    if (!hasFiles) {
      let placeholderAdded = false;

      const ctrl = streamMessage(text, {
        onToken: (delta) => {
          if (!placeholderAdded) {
            placeholderAdded = true;
            setThinkingFor(currentSessionId, false);
            appendMessage(currentSessionId, {
              role: "assistant",
              content: "",
              streaming: true,
            });
          }
          appendDelta(currentSessionId, delta);
        },
        onDone: ({ response, tools_used, agents_trace, file_url, tokens_per_second }) => {
          streamAbortRef.current = null;
          if (!placeholderAdded) {
            appendMessage(currentSessionId, {
              role: "assistant",
              content: response,
              tools_used,
              agents_trace,
              file_url,
              tokens_per_second,
            });
          } else {
            finalizeLastMessage(currentSessionId, {
              content: response,
              tools_used,
              agents_trace,
              file_url,
              tokens_per_second,
            });
          }
          onReply?.(response);
          setThinkingFor(currentSessionId, false);
          inputRef.current?.focus();
        },
        onError: (msg) => {
          setError(msg);
          setThinkingFor(currentSessionId, false);
          streamAbortRef.current = null;
          inputRef.current?.focus();
        },
      });
      streamAbortRef.current = ctrl;
    } else {
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
          onReply?.(reply);
          setThinkingFor(currentSessionId, false);
          inputRef.current?.focus();
        } catch (e) {
          if (e.message === "Failed to fetch") {
            setTimeout(tryFetch, 3000);
          } else {
            setError(e.message);
            setThinkingFor(currentSessionId, false);
            inputRef.current?.focus();
          }
        }
      };

      tryFetch();
    }
  }

  return {
    thinking,
    error,
    setError,
    handleSend,
    handleEscape,
  };
}
