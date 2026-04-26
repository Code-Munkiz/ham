/**
 * Manual Browser Operator proposals — War Room only. Structured actions only (no NL, no selector-click v1).
 */
import * as React from "react";
import { Loader2 } from "lucide-react";
import {
  createBrowserProposal,
  type BrowserProposalActionPayload,
  type BrowserProposalActionType,
} from "@/lib/ham/api";
import { cn } from "@/lib/utils";

const ACTION_OPTIONS: Array<{ value: BrowserProposalActionType; label: string }> = [
  { value: "browser.navigate", label: "Open page (URL)" },
  { value: "browser.click_xy", label: "Pointer tap (x, y)" },
  { value: "browser.scroll", label: "Scroll (deltas)" },
  { value: "browser.key", label: "Key" },
  { value: "browser.type", label: "Type into selector" },
  { value: "browser.reset", label: "Reset viewport" },
];

export interface BrowserProposeFormProps {
  sessionId: string;
  ownerKey: string;
  disabled?: boolean;
  onProposed?: () => void;
}

export function BrowserProposeForm({ sessionId, ownerKey, disabled, onProposed }: BrowserProposeFormProps) {
  const [actionType, setActionType] = React.useState<BrowserProposalActionType>("browser.navigate");
  const [url, setUrl] = React.useState("");
  const [x, setX] = React.useState("100");
  const [y, setY] = React.useState("80");
  const [deltaX, setDeltaX] = React.useState("0");
  const [deltaY, setDeltaY] = React.useState("100");
  const [key, setKey] = React.useState("Enter");
  const [selector, setSelector] = React.useState("input");
  const [text, setText] = React.useState("");
  const [clearFirst, setClearFirst] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  async function handlePropose(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    let action: BrowserProposalActionPayload;
    switch (actionType) {
      case "browser.navigate":
        if (!url.trim()) {
          setErr("URL is required for Open page.");
          return;
        }
        action = { action_type: "browser.navigate", url: url.trim() };
        break;
      case "browser.click_xy": {
        const px = Number.parseFloat(x);
        const py = Number.parseFloat(y);
        if (Number.isNaN(px) || Number.isNaN(py)) {
          setErr("x and y must be numbers.");
          return;
        }
        action = {
          action_type: "browser.click_xy",
          x: px,
          y: py,
        };
        break;
      }
      case "browser.scroll":
        action = {
          action_type: "browser.scroll",
          delta_x: Number.parseFloat(deltaX) || 0,
          delta_y: Number.parseFloat(deltaY) || 0,
        };
        break;
      case "browser.key":
        action = { action_type: "browser.key", key: key.trim() };
        break;
      case "browser.type":
        action = {
          action_type: "browser.type",
          selector: selector.trim(),
          text,
          clear_first: clearFirst,
        };
        break;
      case "browser.reset":
        action = { action_type: "browser.reset" };
        break;
      default:
        return;
    }
    setBusy(true);
    try {
      await createBrowserProposal({
        session_id: sessionId,
        owner_key: ownerKey,
        action,
        proposer: { kind: "operator", label: "war-room" },
      });
      onProposed?.();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Propose failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={(ev) => void handlePropose(ev)}
      className="rounded border border-white/10 bg-black/30 p-2 space-y-2 text-[10px]"
    >
      <p className="text-[9px] font-black uppercase tracking-wider text-[#00E5FF]/70">
        Propose browser action
      </p>
      <label className="block space-y-0.5">
        <span className="text-white/35">Action</span>
        <select
          value={actionType}
          onChange={(e) => setActionType(e.target.value as BrowserProposalActionType)}
          disabled={disabled || busy}
          className="w-full bg-black/60 border border-white/15 rounded px-1.5 py-1 text-white/80"
        >
          {ACTION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      {actionType === "browser.navigate" ? (
        <label className="block space-y-0.5">
          <span className="text-white/35">URL</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={disabled || busy}
            className="w-full font-mono bg-black/60 border border-white/15 rounded px-1.5 py-1 text-white/80"
            placeholder="https://…"
          />
        </label>
      ) : null}

      {actionType === "browser.click_xy" ? (
        <div className="flex gap-2">
          <label className="flex-1 space-y-0.5">
            <span className="text-white/35">x</span>
            <input
              value={x}
              onChange={(e) => setX(e.target.value)}
              disabled={disabled || busy}
              className="w-full font-mono bg-black/60 border border-white/15 rounded px-1.5 py-1"
            />
          </label>
          <label className="flex-1 space-y-0.5">
            <span className="text-white/35">y</span>
            <input
              value={y}
              onChange={(e) => setY(e.target.value)}
              disabled={disabled || busy}
              className="w-full font-mono bg-black/60 border border-white/15 rounded px-1.5 py-1"
            />
          </label>
        </div>
      ) : null}

      {actionType === "browser.scroll" ? (
        <div className="flex gap-2">
          <label className="flex-1 space-y-0.5">
            <span className="text-white/35">delta X</span>
            <input
              value={deltaX}
              onChange={(e) => setDeltaX(e.target.value)}
              disabled={disabled || busy}
              className="w-full font-mono bg-black/60 border border-white/15 rounded px-1.5 py-1"
            />
          </label>
          <label className="flex-1 space-y-0.5">
            <span className="text-white/35">delta Y</span>
            <input
              value={deltaY}
              onChange={(e) => setDeltaY(e.target.value)}
              disabled={disabled || busy}
              className="w-full font-mono bg-black/60 border border-white/15 rounded px-1.5 py-1"
            />
          </label>
        </div>
      ) : null}

      {actionType === "browser.key" ? (
        <label className="block space-y-0.5">
          <span className="text-white/35">Key</span>
          <input
            value={key}
            onChange={(e) => setKey(e.target.value)}
            disabled={disabled || busy}
            className="w-full bg-black/60 border border-white/15 rounded px-1.5 py-1"
          />
        </label>
      ) : null}

      {actionType === "browser.type" ? (
        <div className="space-y-1">
          <label className="block space-y-0.5">
            <span className="text-white/35">Selector</span>
            <input
              value={selector}
              onChange={(e) => setSelector(e.target.value)}
              disabled={disabled || busy}
              className="w-full font-mono bg-black/60 border border-white/15 rounded px-1.5 py-1"
            />
          </label>
          <label className="block space-y-0.5">
            <span className="text-white/35">Text</span>
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={disabled || busy}
              className="w-full bg-black/60 border border-white/15 rounded px-1.5 py-1"
            />
          </label>
          <label className="flex items-center gap-2 text-white/50">
            <input
              type="checkbox"
              checked={clearFirst}
              onChange={(e) => setClearFirst(e.target.checked)}
              disabled={disabled || busy}
            />
            Clear field first
          </label>
        </div>
      ) : null}

      {err ? <p className="text-amber-400/90 text-[9px] font-mono">{err}</p> : null}

      <button
        type="submit"
        disabled={disabled || busy}
        className={cn(
          "w-full text-[9px] font-black uppercase tracking-widest py-1.5 rounded border",
          disabled || busy
            ? "text-white/25 border-white/10"
            : "text-[#00E5FF] border-[#00E5FF]/35 hover:bg-[#00E5FF]/5",
        )}
      >
        {busy ? (
          <span className="inline-flex items-center justify-center gap-1">
            <Loader2 className="h-3 w-3 animate-spin" /> Working…
          </span>
        ) : (
          "Propose"
        )}
      </button>
    </form>
  );
}
