/**
 * Full-screen entry: Ham astrochimp art + typewriter "go ham" + terminal cursor.
 * Click the image (or press Enter / Space when focused) to open Chat.
 */
import * as React from "react";
import { useNavigate } from "react-router-dom";

const LINE = "go ham";
const TYPE_MS = 95;
const CURSOR_BLINK_MS = 530;

export default function Landing() {
  const navigate = useNavigate();
  const [shown, setShown] = React.useState("");
  const [typingDone, setTypingDone] = React.useState(false);
  const [cursorOn, setCursorOn] = React.useState(true);

  React.useEffect(() => {
    if (shown.length >= LINE.length) {
      setTypingDone(true);
      return;
    }
    const t = window.setTimeout(() => {
      setShown(LINE.slice(0, shown.length + 1));
    }, TYPE_MS);
    return () => window.clearTimeout(t);
  }, [shown]);

  React.useEffect(() => {
    if (!typingDone) return;
    const id = window.setInterval(() => setCursorOn((v) => !v), CURSOR_BLINK_MS);
    return () => window.clearInterval(id);
  }, [typingDone]);

  const goChat = React.useCallback(() => {
    navigate("/chat");
  }, [navigate]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      goChat();
    }
  };

  return (
    <div
      className="min-h-screen w-full bg-black flex flex-col items-center justify-center gap-10 px-6 py-12 selection:bg-[#FF6B00]/30"
      role="presentation"
    >
      <button
        type="button"
        onClick={goChat}
        onKeyDown={onKeyDown}
        className="group relative max-w-[min(92vw,420px)] w-full rounded-lg border border-white/5 bg-black p-2 shadow-[0_0_60px_rgba(255,107,0,0.08)] transition-all duration-300 hover:border-[#FF6B00]/35 hover:shadow-[0_0_80px_rgba(255,107,0,0.15)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
        aria-label="Enter Ham — open chat"
      >
        <img
          src="/ham-landing.png"
          alt="Ham — terminal-style astrochimp portrait"
          className="w-full h-auto object-contain pointer-events-none select-none"
          draggable={false}
        />
      </button>

      <div
        className="font-mono text-sm sm:text-base tracking-wide text-[#FF6B00]/90 min-h-[1.5rem] flex items-center justify-center gap-0.5"
        aria-live="polite"
      >
        <span className="text-white/50 mr-1 select-none">$</span>
        <span>{shown}</span>
        <span
          className="inline-block w-2.5 h-4 sm:h-5 align-middle bg-[#FF6B00] transition-opacity duration-75"
          style={{ opacity: typingDone ? (cursorOn ? 1 : 0) : 1 }}
          aria-hidden
        />
      </div>

      <p className="text-[10px] font-mono uppercase tracking-[0.35em] text-white/25">
        click image to continue
      </p>
    </div>
  );
}
