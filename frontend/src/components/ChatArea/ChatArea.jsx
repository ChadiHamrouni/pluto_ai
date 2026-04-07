import "./ChatArea.css";

import StatusLabel from "../StatusLabel";
import ChatBubble from "../ChatBubble";
import VoiceOverlay from "../VoiceOverlay";

const THINKING_WORDS = [
    "يا قمر الليل", "ليلة و المزود خدام",
  "ام الشعور السود", "نمدح الأقطاب ", "يامه الأسمر دوني",
];

export default function ChatArea({
  messages,
  messagesLoading,
  thinking,
  error,
  onDownload,
  bottomRef,
  voiceMode,
  recording,
  transcribing,
  speaking,
  lastTranscript,
  onExitVoice,
}) {
  if (voiceMode) {
    return (
      <VoiceOverlay
        recording={recording}
        transcribing={transcribing}
        thinking={thinking}
        speaking={speaking}
        lastTranscript={lastTranscript}
        onExit={onExitVoice}
      />
    );
  }

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
