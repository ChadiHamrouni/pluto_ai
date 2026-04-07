/**
 * useChat — handles sending messages via normal chat or streaming.
 */

import { useRef, useState } from "react";
import { sendMessage, streamMessage } from "../api";

export function useChat({ activeId, messages, appendMessage, appendDelta, finalizeLastMessage, updateSession, onReply }) {
  const [thinking, setThinking]     = useState(false);
  const [error, setError]           = useState(null);

  const streamAbortRef = useRef(null);

  async function handleEscape() {
    if (!thinking) return;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setThinking(false);
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
    setThinking(true);

    const currentSessionId = activeId;
    const hasFiles = sentAttachments.length > 0;

    if (!hasFiles) {
      let placeholderAdded = false;

      const ctrl = streamMessage(text, {
        onToken: (delta) => {
          if (!placeholderAdded) {
            placeholderAdded = true;
            setThinking(false);
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
          setThinking(false);
          inputRef.current?.focus();
        },
        onError: (msg) => {
          setError(msg);
          setThinking(false);
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
  }

  return {
    thinking,
    error,
    setError,
    handleSend,
    handleEscape,
  };
}
