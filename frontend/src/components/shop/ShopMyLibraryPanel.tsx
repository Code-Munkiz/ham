/**
 * My Library — project-scoped saved catalog references (read + token-gated save/remove).
 */
import * as React from "react";
import { Bookmark, KeyRound, RefreshCw, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  fetchCapabilityLibrary,
  fetchCapabilityLibraryAggregate,
  fetchCapabilityLibraryWriteStatus,
  postCapabilityLibraryRemove,
  type CapabilityLibraryAggregateResponse,
} from "@/lib/ham/api";

export interface ShopMyLibraryPanelProps {
  projectId: string | null;
  writeToken: string;
  onWriteTokenChange: (t: string) => void;
  onRevisionRef?: React.MutableRefObject<string | null>;
}

export function ShopMyLibraryPanel({
  projectId,
  writeToken,
  onWriteTokenChange,
  onRevisionRef,
}: ShopMyLibraryPanelProps) {
  const [writeStatus, setWriteStatus] = React.useState<{ writes_enabled: boolean } | null>(null);
  const [agg, setAgg] = React.useState<CapabilityLibraryAggregateResponse | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [busyRef, setBusyRef] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    if (!projectId) {
      setAgg(null);
      setErr(null);
      return;
    }
    setLoading(true);
    setErr(null);
    try {
      const [ws, a] = await Promise.all([
        fetchCapabilityLibraryWriteStatus(),
        fetchCapabilityLibraryAggregate(projectId),
      ]);
      setWriteStatus(ws);
      setAgg(a);
      if (onRevisionRef) onRevisionRef.current = a.revision;
    } catch (e) {
      setAgg(null);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, onRevisionRef]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const remove = async (ref: string) => {
    if (!projectId || !writeToken.trim() || !agg) return;
    setBusyRef(ref);
    setErr(null);
    try {
      const lib = await fetchCapabilityLibrary(projectId);
      await postCapabilityLibraryRemove(
        projectId,
        { ref, base_revision: lib.revision },
        writeToken.trim(),
      );
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyRef(null);
    }
  };

  if (!projectId) {
    return (
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-[11px] text-amber-100/90 max-w-2xl">
        Add a registered project to the URL:{" "}
        <span className="font-mono text-white/80">?project_id=…</span> (e.g. from Chat workspace). Library
        entries live under that project&rsquo;s <span className="font-mono">.ham</span> on the API host.
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="flex flex-col sm:flex-row sm:items-end gap-4">
        <div className="flex-1 space-y-1.5">
          <span className="text-[9px] font-black uppercase tracking-widest text-white/35 flex items-center gap-2">
            <KeyRound className="h-3.5 w-3.5" />
            HAM_CAPABILITY_LIBRARY_WRITE_TOKEN
          </span>
          <Input
            type="password"
            value={writeToken}
            onChange={(e) => onWriteTokenChange(e.target.value)}
            placeholder="Paste write token to save or remove (session only)"
            className="bg-black/50 border-white/10 text-white text-xs h-9 font-mono"
            autoComplete="off"
          />
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className={cn(
            "shrink-0 flex items-center justify-center gap-2 px-4 py-2 rounded-lg border text-[10px] font-black uppercase tracking-widest",
            "border-white/15 text-white/55 hover:text-white/80 hover:border-white/25",
          )}
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {writeStatus && !writeStatus.writes_enabled ? (
        <p className="text-[10px] text-amber-200/80 font-mono">
          API has no <span className="font-black">HAM_CAPABILITY_LIBRARY_WRITE_TOKEN</span> — saves are disabled
          on this service.
        </p>
      ) : null}

      {err ? (
        <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-red-200/90 text-xs">
          {err}
        </div>
      ) : null}

      {loading && !agg ? <p className="text-[10px] text-white/40 font-bold uppercase tracking-widest">Loading…</p> : null}

      {agg ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[10px] text-white/40">
            <Bookmark className="h-3.5 w-3.5 text-[#FF6B00]/80" />
            <span className="font-mono">revision {agg.revision.slice(0, 12)}…</span>
            <span className="text-white/25">·</span>
            <span>
              {agg.entry_count} saved — this does <span className="text-white/55">not</span> install anything.
            </span>
          </div>
          {agg.items.length === 0 ? (
            <p className="text-[11px] text-white/40 leading-relaxed">
              Nothing saved yet. Open the <span className="text-[#FF6B00]/80 font-semibold">Skills</span> tab and
              use &ldquo;Save to My Library&rdquo; on a catalog card.
            </p>
          ) : (
            <ul className="space-y-2">
              {agg.items.map((it) => (
                <li
                  key={it.ref}
                  className="rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:justify-between"
                >
                  <div className="min-w-0 space-y-1">
                    <p className="text-[10px] font-mono text-[#FF6B00]/90 truncate">{it.ref}</p>
                    {typeof it.hermes?.display_name === "string" ? (
                      <p className="text-xs text-white/80 truncate">{it.hermes.display_name}</p>
                    ) : null}
                    {typeof it.capability_directory?.display_name === "string" ? (
                      <p className="text-xs text-white/80 truncate">{it.capability_directory.display_name}</p>
                    ) : null}
                    {it.library.notes ? (
                      <p className="text-[10px] text-white/40">{it.library.notes}</p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    disabled={!writeToken.trim() || busyRef === it.ref}
                    onClick={() => void remove(it.ref)}
                    className={cn(
                      "shrink-0 text-[9px] font-black uppercase tracking-widest px-3 py-1.5 rounded border flex items-center gap-1.5",
                      writeToken.trim()
                        ? "border-red-500/35 text-red-200/80 hover:border-red-500/55"
                        : "border-white/10 text-white/30 cursor-not-allowed",
                    )}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
