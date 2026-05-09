/**
 * Shared create-workspace modal (portal). Used by the workspace pill and sidebar.
 */
import * as React from "react";
import { createPortal } from "react-dom";

import { WorkspaceOnboardingScreen } from "@/components/workspace/WorkspaceOnboardingScreen";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import type { HamCreateWorkspaceBody, HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

export interface WorkspaceCreateWorkspaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fires after a successful create, before the dialog closes. */
  onCreated?: (workspace: HamWorkspaceSummary) => void;
}

export function WorkspaceCreateWorkspaceDialog({
  open,
  onOpenChange,
  onCreated,
}: WorkspaceCreateWorkspaceDialogProps) {
  const ctx = useHamWorkspace();
  const me =
    ctx.state.status === "ready" || ctx.state.status === "onboarding" ? ctx.state.me : null;

  React.useEffect(() => {
    if (!open) return;
    function onKey(ev: KeyboardEvent) {
      if (ev.key === "Escape") onOpenChange(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const handleCreate = async (body: HamCreateWorkspaceBody) => {
    const ws = await ctx.createWorkspace(body);
    onCreated?.(ws);
    onOpenChange(false);
    return ws;
  };

  if (!open || !me || typeof document === "undefined") return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ham-workspace-create-title"
      data-testid="ham-workspace-create-dialog"
      onClick={(ev) => {
        if (ev.target === ev.currentTarget) onOpenChange(false);
      }}
    >
      <WorkspaceOnboardingScreen
        user={me.user}
        orgs={me.orgs}
        onCreate={handleCreate}
        onDismiss={() => onOpenChange(false)}
        allowDismiss
        variant="dialog"
        showInstructionsField
        showConnectedToolsHint
      />
    </div>,
    document.body,
  );
}
