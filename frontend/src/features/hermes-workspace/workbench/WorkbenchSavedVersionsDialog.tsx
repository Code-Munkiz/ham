import * as React from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import {
  listBuilderProjectSources,
  listBuilderSourceSnapshots,
  type BuilderProjectSourceRecord,
  type BuilderSourceSnapshotRecord,
} from "@/lib/ham/api";
import {
  formatSavedVersionCreatedAt,
  sanitizeSavedVersionsErrorMessage,
  savedVersionFileCount,
  savedVersionFilesChangedCopy,
  savedVersionLabel,
  sortSavedVersionsNewestFirst,
} from "@/lib/ham/workbenchSavedVersions";

export type WorkbenchSavedVersionsDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId?: string | null;
  projectId?: string | null;
  refreshKey?: number;
  onViewVersion?: (snapshotId: string) => void;
};

export function WorkbenchSavedVersionsDialog({
  open,
  onOpenChange,
  workspaceId = null,
  projectId = null,
  refreshKey = 0,
  onViewVersion,
}: WorkbenchSavedVersionsDialogProps) {
  const [snapshots, setSnapshots] = React.useState<BuilderSourceSnapshotRecord[]>([]);
  const [sources, setSources] = React.useState<BuilderProjectSourceRecord[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const ws = workspaceId?.trim() || "";
  const pid = projectId?.trim() || "";

  React.useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onOpenChange(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  React.useEffect(() => {
    if (!open) return;
    if (!ws || !pid) {
      setSnapshots([]);
      setSources([]);
      setLoadError(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void (async () => {
      try {
        const [snapshotsRes, sourcesRes] = await Promise.all([
          listBuilderSourceSnapshots(ws, pid),
          listBuilderProjectSources(ws, pid),
        ]);
        if (cancelled) return;
        setSnapshots(snapshotsRes.source_snapshots || []);
        setSources(sourcesRes.sources || []);
      } catch (e) {
        if (cancelled) return;
        setSnapshots([]);
        setSources([]);
        setLoadError(sanitizeSavedVersionsErrorMessage(e instanceof Error ? e.message : String(e)));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, ws, pid, refreshKey]);

  const activeSnapshotId =
    sources.find((source) => source.active_snapshot_id)?.active_snapshot_id ?? null;
  const sortedSnapshots = sortSavedVersionsNewestFirst(snapshots);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[450] flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="hww-saved-versions-title"
      data-testid="hww-saved-versions-dialog"
      onClick={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
    >
      <div
        className="max-h-[min(90vh,40rem)] w-full max-w-lg overflow-y-auto rounded-xl border border-white/[0.1] bg-[#07141c] p-5 text-left shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-3">
          <div>
            <h2 id="hww-saved-versions-title" className="text-base font-semibold text-white/95">
              Saved versions
            </h2>
            <p className="mt-1 text-[11px] leading-relaxed text-white/45">
              Each time HAM saves your project files, a version appears here. View files in the Code
              tab — restore is not available in this beta build.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 shrink-0 text-white/60 hover:text-white"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
        </div>

        <div className="mt-4 space-y-3 text-[12px] leading-relaxed text-white/70">
          {!ws || !pid ? (
            <p className="text-white/55" data-testid="hww-saved-versions-no-project">
              Select a workspace and project in chat to see saved versions.
            </p>
          ) : null}

          {ws && pid && loading ? (
            <p className="text-white/45" data-testid="hww-saved-versions-loading">
              Loading saved versions…
            </p>
          ) : null}

          {ws && pid && loadError ? (
            <p className="text-amber-200/90" data-testid="hww-saved-versions-error">
              {loadError}
            </p>
          ) : null}

          {ws && pid && !loading && !loadError && sortedSnapshots.length === 0 ? (
            <p className="text-white/55" data-testid="hww-saved-versions-empty">
              No saved versions yet. Ask HAM to build something and your first version will appear
              here.
            </p>
          ) : null}

          {ws && pid && !loading && !loadError && sortedSnapshots.length > 0 ? (
            <ul className="space-y-2" data-testid="hww-saved-versions-list">
              {sortedSnapshots.map((snapshot, index) => {
                const fileCount = savedVersionFileCount(snapshot);
                const filesCopy = savedVersionFilesChangedCopy(fileCount);
                const isCurrent = Boolean(activeSnapshotId && snapshot.id === activeSnapshotId);
                return (
                  <li
                    key={snapshot.id}
                    className="rounded-lg border border-white/[0.08] bg-black/25 p-3"
                    data-testid={`hww-saved-version-row-${index}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p
                          className="text-[13px] font-medium text-white/88"
                          data-testid={`hww-saved-version-label-${index}`}
                        >
                          {savedVersionLabel(snapshot, { isCurrent, sequence: index + 1 })}
                        </p>
                        <p className="mt-1 text-[11px] text-white/45">
                          Created{" "}
                          <span data-testid={`hww-saved-version-created-${index}`}>
                            {formatSavedVersionCreatedAt(snapshot.created_at)}
                          </span>
                        </p>
                        {filesCopy ? (
                          <p
                            className="mt-1 text-[11px] text-white/50"
                            data-testid={`hww-saved-version-files-${index}`}
                          >
                            Files changed: {filesCopy}
                          </p>
                        ) : null}
                      </div>
                      {onViewVersion ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          className="shrink-0 text-[11px]"
                          data-testid={`hww-saved-version-view-${index}`}
                          onClick={() => onViewVersion(snapshot.id)}
                        >
                          View in Code
                        </Button>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
