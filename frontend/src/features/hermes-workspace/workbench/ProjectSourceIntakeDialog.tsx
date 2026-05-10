/**
 * Shared "Add project source" flow for the workbench. Honest about what each path does:
 * - Local workspace upload: real when local runtime + `/api/workspace/files/upload` (disk only).
 * - Chat attachment upload: real `POST /api/chat/attachments` for composer/message context — not project indexing.
 * - ZIP / GitHub repo import: not wired — disabled or links only.
 */
import * as React from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { fetchWorkspaceTools, postChatUploadAttachment } from "@/lib/ham/api";
import { workspaceFileAdapter } from "../adapters/filesAdapter";
import { isLocalRuntimeConfigured } from "../adapters/localRuntime";

export const WORKBENCH_CONNECTED_TOOLS_HREF = "/workspace/settings?section=tools";
export const WORKBENCH_CONNECTION_SETTINGS_HREF = "/workspace/settings?section=connection";

type ToolDiscoveryResponse = {
  tools: Array<{
    id: string;
    connection?: "on" | "off" | "error";
    status?: string;
  }>;
};

export type ProjectSourceIntakeDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function githubConnectionFromPayload(
  data: ToolDiscoveryResponse | null,
): "on" | "off" | "error" | null {
  if (!data?.tools) return null;
  const gh = data.tools.find((t) => t.id === "github");
  if (!gh) return null;
  if (gh.connection) return gh.connection;
  if (gh.status === "error") return "error";
  if (gh.status === "ready") return "on";
  return "off";
}

export function ProjectSourceIntakeDialog({ open, onOpenChange }: ProjectSourceIntakeDialogProps) {
  const [toolsPayload, setToolsPayload] = React.useState<ToolDiscoveryResponse | null>(null);
  const [toolsError, setToolsError] = React.useState<string | null>(null);
  const [workspaceBusy, setWorkspaceBusy] = React.useState(false);
  const [chatBusy, setChatBusy] = React.useState(false);
  const [statusLines, setStatusLines] = React.useState<string[]>([]);

  const wsInputRef = React.useRef<HTMLInputElement>(null);
  const chatInputRef = React.useRef<HTMLInputElement>(null);

  const localRuntimeReady = isLocalRuntimeConfigured();
  const ghConn = githubConnectionFromPayload(toolsPayload);

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
    setStatusLines([]);
    setToolsError(null);
    let cancelled = false;
    void (async () => {
      try {
        const resp = await fetchWorkspaceTools();
        if (!resp.ok) {
          if (!cancelled) setToolsError(`Could not load tool status (HTTP ${resp.status}).`);
          return;
        }
        const json = (await resp.json()) as ToolDiscoveryResponse;
        if (!cancelled) setToolsPayload(json);
      } catch {
        if (!cancelled) setToolsError("Could not load tool status.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const appendStatus = (line: string) => {
    setStatusLines((prev) => [...prev, line].slice(-12));
  };

  const onWorkspaceFilesSelected = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const files = ev.target.files;
    ev.target.value = "";
    if (!files?.length) return;
    setWorkspaceBusy(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file, file.name);
        const { ok, bridge, error } = await workspaceFileAdapter.postFormData(form);
        if (ok) {
          appendStatus(`Workspace file saved: ${file.name}`);
        } else {
          const bridgeDetail =
            bridge.status === "pending" && "detail" in bridge ? bridge.detail : undefined;
          appendStatus(
            `Workspace upload failed (${file.name}): ${error ?? bridgeDetail ?? "unknown error"}`,
          );
        }
      }
    } finally {
      setWorkspaceBusy(false);
    }
  };

  const onChatFileSelected = async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    setChatBusy(true);
    try {
      const meta = await postChatUploadAttachment(file);
      appendStatus(`Chat attachment stored: ${meta.filename} (${meta.kind})`);
    } catch (e) {
      appendStatus(`Chat attachment failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setChatBusy(false);
    }
  };

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[450] flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="hww-project-source-title"
      data-testid="hww-project-source-dialog"
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
            <h2 id="hww-project-source-title" className="text-base font-semibold text-white/95">
              Add project source
            </h2>
            <p className="mt-1 text-[11px] leading-relaxed text-white/45">
              Bring files or credentials into HAM. Only describe capabilities that exist — no
              implied project scan or repo analysis from this dialog alone.
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

        <div className="mt-4 space-y-4 text-[12px] leading-relaxed text-white/70">
          <section className="rounded-lg border border-white/[0.08] bg-black/25 p-3">
            <h3 className="text-[12px] font-semibold text-white/88">
              Upload files (local workspace)
            </h3>
            <p className="mt-1 text-[11px] text-white/45">
              Writes through your <span className="text-white/55">connected local HAM API</span>{" "}
              into <span className="font-medium text-white/60">HAM_WORKSPACE_ROOT</span> (or the
              sandbox root). Files appear in{" "}
              <Link
                to="/workspace/files"
                className="text-[#7dd3fc] underline-offset-2 hover:underline"
              >
                Files
              </Link>
              .{" "}
              <span className="text-white/50">
                Automatic project context from these file paths is not wired.
              </span>
            </p>
            <input
              ref={wsInputRef}
              type="file"
              multiple
              className="hidden"
              data-testid="hww-project-source-workspace-file-input"
              onChange={(e) => void onWorkspaceFilesSelected(e)}
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="mt-2 text-[11px]"
              disabled={!localRuntimeReady || workspaceBusy}
              data-testid="hww-project-source-workspace-upload-btn"
              onClick={() => wsInputRef.current?.click()}
            >
              {workspaceBusy ? "Uploading…" : "Choose files for workspace disk"}
            </Button>
            {!localRuntimeReady ? (
              <p className="mt-2 text-[11px] text-amber-200/80">
                Local API not configured. Set your local runtime URL in{" "}
                <Link
                  to={WORKBENCH_CONNECTION_SETTINGS_HREF}
                  className="font-medium text-[#7dd3fc] underline-offset-2 hover:underline"
                  data-testid="hww-project-source-connection-link"
                >
                  Settings → Connection
                </Link>
                .
              </p>
            ) : null}
          </section>

          <section className="rounded-lg border border-white/[0.08] bg-black/25 p-3">
            <h3 className="text-[12px] font-semibold text-white/88">
              Upload files (chat attachment)
            </h3>
            <p className="mt-1 text-[11px] text-white/45">
              Uses <span className="font-medium text-white/60">POST /api/chat/attachments</span>.
              Stored for use with chat messages —{" "}
              <span className="text-white/50">not a full project mount on disk.</span>
            </p>
            <input
              ref={chatInputRef}
              type="file"
              className="hidden"
              data-testid="hww-project-source-chat-file-input"
              onChange={(e) => void onChatFileSelected(e)}
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="mt-2 text-[11px]"
              disabled={chatBusy}
              data-testid="hww-project-source-chat-upload-btn"
              onClick={() => chatInputRef.current?.click()}
            >
              {chatBusy ? "Uploading…" : "Choose file for chat attachment"}
            </Button>
          </section>

          <section className="rounded-lg border border-white/[0.08] bg-black/25 p-3">
            <h3 className="text-[12px] font-semibold text-white/88">Upload ZIP</h3>
            <p className="mt-1 text-[11px] text-white/45">
              ZIP extraction and bulk project ingest are not implemented in the API.
            </p>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled
              className="mt-2 text-[11px]"
            >
              Upload ZIP — Coming soon
            </Button>
          </section>

          <section className="rounded-lg border border-white/[0.08] bg-black/25 p-3">
            <h3 className="text-[12px] font-semibold text-white/88">GitHub</h3>
            {toolsError ? (
              <p className="mt-1 text-[11px] text-amber-200/80">{toolsError}</p>
            ) : (
              <p className="mt-1 text-[11px] text-white/45">
                GitHub credential status:{" "}
                {ghConn === "on" ? (
                  <span className="text-emerald-200/90">token connected (Connected Tools)</span>
                ) : ghConn === "error" ? (
                  <span className="text-amber-200/90">needs attention in Connected Tools</span>
                ) : ghConn === "off" ? (
                  <span className="text-white/50">not connected</span>
                ) : (
                  <span className="text-white/50">unknown</span>
                )}
                . Repository clone/import from this dialog is{" "}
                <span className="text-white/50">not wired</span>.
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="secondary" asChild className="text-[11px]">
                <Link
                  to={WORKBENCH_CONNECTED_TOOLS_HREF}
                  data-testid="hww-project-source-connected-tools-link"
                >
                  Open Connected Tools
                </Link>
              </Button>
              <Button type="button" size="sm" variant="secondary" disabled className="text-[11px]">
                Import repository — Coming soon
              </Button>
            </div>
            <label className="mt-3 block text-[10px] font-medium uppercase tracking-wide text-white/40">
              Paste repo URL
            </label>
            <input
              type="url"
              disabled
              placeholder="https://github.com/org/repo"
              className="mt-1 w-full cursor-not-allowed rounded-md border border-white/[0.08] bg-black/40 px-2 py-1.5 text-[11px] text-white/35"
              data-testid="hww-project-source-repo-url-input"
            />
            <p className="mt-1 text-[10px] text-white/35">
              URL import is not available — field disabled.
            </p>
          </section>

          {statusLines.length > 0 ? (
            <div
              className="rounded-lg border border-white/[0.06] bg-black/35 px-3 py-2 text-[11px] text-white/60"
              data-testid="hww-project-source-status-log"
            >
              <p className="font-medium text-white/70">Recent actions</p>
              <ul className="mt-1 list-inside list-disc space-y-0.5">
                {statusLines.map((line, i) => (
                  <li key={`${i}-${line.slice(0, 24)}`}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
