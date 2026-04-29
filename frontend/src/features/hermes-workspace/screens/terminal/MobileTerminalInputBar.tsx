import * as React from "react";
import { ArrowUp, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = {
  onSend: (line: string) => void;
  onCtrlC: () => void;
};

/**
 * Isolated from main terminal to avoid re-render thrash; mirrors upstream
 * `mobile-terminal-input` affordances.
 */
export function MobileTerminalInputBar({ onSend, onCtrlC }: Props) {
  const ref = React.useRef<HTMLInputElement | null>(null);

  const send = () => {
    const v = ref.current?.value;
    if (!v) return;
    onSend(v + "\n");
    if (ref.current) {
      ref.current.value = "";
    }
  };

  const paste = async () => {
    try {
      const t = await navigator.clipboard.readText();
      if (t && ref.current) {
        ref.current.value += t;
        ref.current.focus();
      }
    } catch {
      ref.current?.focus();
    }
  };

  return (
    <div
      className="flex shrink-0 items-center gap-1 border-t border-[#333] px-2 py-1.5"
      style={{ background: "#1a1a1a" }}
    >
      <Button
        type="button"
        size="icon"
        variant="secondary"
        className="h-8 w-8 shrink-0 text-white/50"
        onClick={() => void paste()}
        aria-label="Paste"
      >
        <Copy className="h-4 w-4" />
      </Button>
      <input
        ref={ref}
        type="text"
        defaultValue=""
        placeholder="Type command…"
        className="min-w-0 flex-1 rounded-md border border-[#444] bg-[#2a2a2a] px-2 py-1 font-mono text-[12px] text-[#e6e6e6] outline-none"
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            send();
          }
          if (e.key === "Tab") {
            e.preventDefault();
            onSend("\t");
          }
        }}
      />
      <Button
        type="button"
        size="sm"
        variant="secondary"
        className="h-8 shrink-0 bg-[#3a1a1a] px-2 text-xs text-red-300"
        onClick={onCtrlC}
        aria-label="Ctrl+C"
      >
        ^C
      </Button>
      <Button
        type="button"
        size="icon"
        className="h-8 w-8 shrink-0 bg-[#ea580c] text-white"
        onClick={send}
        aria-label="Send"
      >
        <ArrowUp className="h-4 w-4" />
      </Button>
    </div>
  );
}
