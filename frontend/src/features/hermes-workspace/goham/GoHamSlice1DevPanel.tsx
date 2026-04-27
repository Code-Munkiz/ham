/**
 * Dev-only hooks for GoHAM v1 Slice 1 browser primitives (observe / wait / scroll / enumerated click).
 * Not shown in production builds.
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { getHamDesktopLocalControlApi } from "@/lib/ham/desktopBundleBridge";
import type { HamDesktopRealBrowserClickCandidate } from "@/lib/ham/desktopBundleBridge";

type GoHamSlice1DevPanelProps = {
  /** When false, render nothing. */
  visible: boolean;
};

export function GoHamSlice1DevPanel({ visible }: GoHamSlice1DevPanelProps) {
  const [log, setLog] = React.useState<string>("");
  const [candidates, setCandidates] = React.useState<HamDesktopRealBrowserClickCandidate[]>([]);
  const [pick, setPick] = React.useState<string>("");

  const append = React.useCallback((line: string) => {
    setLog((p) => (p ? `${p}\n${line}` : line));
  }, []);

  if (!visible) return null;

  const api = getHamDesktopLocalControlApi();
  if (!api || typeof api.realBrowserObserveCompact !== "function") return null;

  return (
    <div className="mx-auto w-full max-w-[40rem] shrink-0 border border-amber-500/20 bg-amber-950/20 px-3 py-2 text-[10px] text-amber-100/90 md:px-6">
      <div className="mb-1 font-semibold uppercase tracking-wide text-amber-200/90">GoHAM dev — Slice 1 primitives</div>
      <p className="mb-2 text-[9px] leading-snug text-amber-100/60">
        Development only. Uses enumerated candidates only — no free-form selectors or coordinates from the model.
      </p>
      <div className="flex flex-wrap gap-1.5">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 rounded-md text-[10px]"
          onClick={() => {
            void (async () => {
              const r = await api.realBrowserObserveCompact();
              append(JSON.stringify(r));
            })();
          }}
        >
          Observe
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 rounded-md text-[10px]"
          onClick={() => {
            void (async () => {
              const r = await api.realBrowserWaitMs(1200);
              append(JSON.stringify(r));
            })();
          }}
        >
          Wait 1.2s
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 rounded-md text-[10px]"
          onClick={() => {
            void (async () => {
              const r = await api.realBrowserScrollVertical(320);
              append(JSON.stringify(r));
            })();
          }}
        >
          Scroll +320
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 rounded-md text-[10px]"
          onClick={() => {
            void (async () => {
              const r = await api.realBrowserScrollVertical(-320);
              append(JSON.stringify(r));
            })();
          }}
        >
          Scroll −320
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 rounded-md text-[10px]"
          onClick={() => {
            void (async () => {
              const r = await api.realBrowserEnumerateClickCandidates();
              append(`candidates: ${JSON.stringify({ ok: r.ok, count: "count" in r ? r.count : 0 })}`);
              if (r.ok) {
                setCandidates(r.candidates);
                setPick(r.candidates[0]?.id ?? "");
              } else {
                setCandidates([]);
                setPick("");
              }
            })();
          }}
        >
          List candidates
        </Button>
      </div>
      {candidates.length > 0 ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1 text-[9px] text-amber-100/70">
            <span>Pick id</span>
            <select
              className="max-w-[14rem] rounded border border-white/15 bg-black/40 px-1 py-0.5 text-[9px] text-white"
              value={pick}
              onChange={(e) => setPick(e.target.value)}
            >
              {candidates.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id} — {c.text.slice(0, 40)}
                </option>
              ))}
            </select>
          </label>
          <Button
            type="button"
            size="sm"
            variant="default"
            className="h-7 rounded-md bg-amber-600 text-[10px] text-black hover:bg-amber-500"
            onClick={() => {
              void (async () => {
                const id = pick.trim();
                if (!id) return;
                const r = await api.realBrowserClickCandidate(id);
                append(JSON.stringify(r));
              })();
            }}
          >
            Click candidate
          </Button>
        </div>
      ) : null}
      {log ? (
        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap rounded border border-white/10 bg-black/30 p-2 font-mono text-[9px] text-white/70">
          {log}
        </pre>
      ) : null}
    </div>
  );
}
