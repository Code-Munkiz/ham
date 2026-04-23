/**
 * Full-screen entry: Ham astrochimp art + typewriter "go ham" + terminal cursor.
 * Web: desktop download CTAs for visitors who have not installed the app.
 * Electron: hero only (users already installed); no downloads or outbound links.
 */
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { HAM_DESKTOP_DOWNLOAD_CTAS } from "@/lib/ham/desktopDownloadCtas";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import { publicAssetUrl } from "@/lib/ham/publicAssets";

const LINE = "go ham";
const TYPE_MS = 95;
const CURSOR_BLINK_MS = 530;

export default function Landing() {
  const navigate = useNavigate();
  const isDesktop = isHamDesktopShell();
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

  const imageFrameClassName =
    "group relative max-w-[min(92vw,420px)] w-full rounded-lg border border-white/5 bg-black p-2 shadow-[0_0_60px_rgba(255,107,0,0.08)] transition-all duration-300 hover:border-[#FF6B00]/35 hover:shadow-[0_0_80px_rgba(255,107,0,0.15)]";

  const hamImg = (
    <img
      src={publicAssetUrl("ham-landing.png")}
      alt="Ham — terminal-style astrochimp portrait"
      className="w-full h-auto object-contain pointer-events-none select-none"
      draggable={false}
    />
  );

  const typewriterLine = (
    <div
      className="font-mono text-sm sm:text-base tracking-wide text-[#FF6B00]/90 min-h-[1.5rem] flex items-center justify-center gap-0.5"
      aria-live="polite"
    >
      <span className="text-white/50 mr-1 select-none">$</span>
      <span>{shown}</span>
      <span
        className="inline-block min-w-[0.6ch] text-[#FF6B00] font-mono transition-opacity duration-75 select-none"
        style={{ opacity: typingDone ? (cursorOn ? 1 : 0) : 1 }}
        aria-hidden
      >
        _
      </span>
    </div>
  );

  if (isDesktop) {
    return (
      <div
        className="min-h-screen w-full bg-black flex flex-col items-center justify-center gap-10 px-6 py-12 selection:bg-[#FF6B00]/30"
        role="presentation"
      >
        <div className={`${imageFrameClassName} border-white/5 shadow-[0_0_60px_rgba(255,107,0,0.08)]`}>
          {hamImg}
        </div>
        {typewriterLine}
      </div>
    );
  }

  return (
    <div
      className="min-h-screen w-full bg-black flex flex-col items-center justify-center gap-8 px-6 py-12 selection:bg-[#FF6B00]/30"
      role="presentation"
    >
      <button
        type="button"
        onClick={goChat}
        onKeyDown={onKeyDown}
        className={`${imageFrameClassName} focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black`}
        aria-label="Enter Ham — open chat"
      >
        {hamImg}
      </button>

      {typewriterLine}

      <section
        className="w-full max-w-[min(92vw,520px)] flex flex-col items-center gap-4"
        aria-labelledby="desktop-cta-heading"
      >
        <div className="text-center space-y-1.5">
          <h1
            id="desktop-cta-heading"
            className="text-base sm:text-lg font-semibold tracking-tight text-white/90"
          >
            Download HAM Desktop
          </h1>
          <p className="text-[11px] sm:text-xs font-mono text-white/40 leading-relaxed max-w-md mx-auto">
            Linux and Windows builds are below (test / internal; unsigned). macOS desktop is coming soon.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 w-full">
          {HAM_DESKTOP_DOWNLOAD_CTAS.map((cta) =>
            cta.available && cta.href.trim() ? (
              <a
                key={cta.platform}
                href={cta.href}
                className="flex flex-col items-center justify-center rounded-lg border border-[#FF6B00]/40 bg-[#FF6B00]/10 px-3 py-3 text-center transition-colors hover:border-[#FF6B00]/60 hover:bg-[#FF6B00]/15 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
                rel="noopener noreferrer"
              >
                <span className="text-sm font-medium text-[#FF6B00]">{cta.label}</span>
                {cta.subtext ? (
                  <span className="text-[10px] font-mono text-white/45 mt-1 leading-tight">{cta.subtext}</span>
                ) : null}
              </a>
            ) : (
              <button
                key={cta.platform}
                type="button"
                disabled
                className="flex flex-col items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-3 text-center cursor-not-allowed opacity-80"
              >
                <span className="text-sm font-medium text-white/35">{cta.label}</span>
                <span className="text-[10px] font-mono text-[#FF6B00]/50 mt-1 uppercase tracking-wider">
                  Coming soon
                </span>
                {cta.subtext ? (
                  <span className="text-[10px] font-mono text-white/30 mt-0.5 leading-tight">{cta.subtext}</span>
                ) : null}
              </button>
            ),
          )}
        </div>

        <button
          type="button"
          onClick={goChat}
          className="text-[11px] font-mono text-white/35 hover:text-[#FF6B00]/80 underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FF6B00]/50 rounded px-1"
        >
          Continue to web app
        </button>
      </section>
    </div>
  );
}
