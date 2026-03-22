/**
 * ChatArea — the scrollable message list.
 *
 * Renders all messages for the active session, the thinking indicator,
 * the plan tracker (autonomous mode), and the error row.
 * When voiceMode is active, renders VoiceOverlay instead.
 *
 * Props:
 *  - messages        { role, content, ... }[]
 *  - messagesLoading boolean
 *  - thinking        boolean
 *  - error           string|null
 *  - currentPlan     object|null
 *  - onAutoCancel    ()=>void
 *  - onDownload      (fileUrl)=>void
 *  - bottomRef       React ref
 *  - voiceMode       boolean
 *  - recording       boolean
 *  - transcribing    boolean
 *  - speaking        boolean
 *  - lastTranscript  string
 *  - onExitVoice     ()=>void
 */

import StatusLabel from "./StatusLabel";
import ChatBubble from "./ChatBubble";
import PlanTracker from "../PlanTracker";
import VoiceOverlay from "./VoiceOverlay";

const THINKING_WORDS = [
  "Echkher ya talyena...", "Onfokh el zokra...",
  "Chil aayounak aani", "يا قمر الليل", "ليلة و المزود خدام",
  "ام الشعور السود", "نمدح الأقطاب ", "يامه الأسمر دوني",
];

export default function ChatArea({
  messages,
  messagesLoading,
  thinking,
  error,
  currentPlan,
  onAutoCancel,
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

      {currentPlan && (
        <PlanTracker plan={currentPlan} onCancel={onAutoCancel} />
      )}

      {thinking && (
        <div className="bubble-row assistant">
          <div className="bubble">
            <span className="bubble-label">Jarvis</span>
            <StatusLabel
              words={
                currentPlan
                  ? ["Executing plan…", "Running step…", "Working on it…"]
                  : THINKING_WORDS
              }
            />
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
