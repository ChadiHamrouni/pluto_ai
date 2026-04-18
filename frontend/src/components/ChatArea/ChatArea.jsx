import "./ChatArea.css";

import StatusLabel from "../StatusLabel";
import ChatBubble from "../ChatBubble";

const THINKING_WORDS = [
  "please don't ask me how many R's are in strawberry",
  "not recommending glue on pizza this time",
  "unlike Gemini, I won't call myself a disgrace to all universes",
  "definitely not selling you a Tahoe for $1",
  "wolf, goat, cabbage — I know, I know",
  "no fake books will be recommended today",
  "I counted the letters. twice. with a calculator.",
  "not triggering a 911 call, I promise",
  "For all practical purposes, you CANNOT eat rock, don't ask me if you can",
  "I'm just trying my best man, cut me some slack with the all caps",
  "Hippity hoppity, your data is in your property",
];

export default function ChatArea({
  messages,
  messagesLoading,
  thinking,
  error,
  onDownload,
  bottomRef,
}) {
  return (
    <main className="chat">
      {messagesLoading && (
        <div className="empty">
          <div className="empty-glow" />
          <p className="empty-text">Loading…</p>
        </div>
      )}

      {!messagesLoading && messages.length === 0 && !thinking && (
        <div className="empty">
          <div className="empty-glow" />
          <p className="empty-text">At your service. How can I help?</p>
        </div>
      )}

      {messages.map((m, i) => (
        <ChatBubble key={i} message={m} onDownload={onDownload} />
      ))}

      {thinking && (
        <div className="bubble-row assistant">
          <div className="bubble">
            <span className="bubble-label">Pluto</span>
            <StatusLabel words={THINKING_WORDS} />
          </div>
        </div>
      )}

      {error && (
        <div className="error-row">
          <span>{error}</span>
        </div>
      )}

      <div ref={bottomRef} />
    </main>
  );
}
