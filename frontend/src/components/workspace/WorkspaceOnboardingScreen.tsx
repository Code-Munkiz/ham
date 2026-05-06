/**
 * Phase 1c: first-run create-workspace screen.
 *
 * Shown via `WorkspaceGate` when `/api/me` returns zero workspaces, or as a
 * dialog from the picker (when the user clicks "+ Create workspace"). Single
 * required field (Name); slug is auto-derived server-side. Org-scoped toggle
 * is rendered only when the caller has a primary org and an `org:admin`
 * membership.
 */
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  HamWorkspaceApiError,
  type HamCreateWorkspaceBody,
  type HamMeOrg,
  type HamMeUser,
  type HamWorkspaceSummary,
} from "@/lib/ham/workspaceApi";

export interface WorkspaceOnboardingScreenProps {
  user: HamMeUser;
  orgs: HamMeOrg[];
  onCreate: (body: HamCreateWorkspaceBody) => Promise<HamWorkspaceSummary>;
  /** Called when the user dismisses (only shown when allowDismiss=true). */
  onDismiss?: () => void;
  allowDismiss?: boolean;
  /** Tighter layout for embedded dialog vs full-screen first-run. */
  variant?: "fullscreen" | "dialog";
}

function adminOrgs(orgs: HamMeOrg[]): HamMeOrg[] {
  return orgs.filter((o) => o.org_role === "org:admin");
}

export function WorkspaceOnboardingScreen({
  user,
  orgs,
  onCreate,
  onDismiss,
  allowDismiss,
  variant = "fullscreen",
}: WorkspaceOnboardingScreenProps) {
  const candidateAdminOrgs = React.useMemo(() => adminOrgs(orgs), [orgs]);
  const defaultOrgId = candidateAdminOrgs[0]?.org_id ?? user.primary_org_id ?? null;
  const [name, setName] = React.useState("");
  const [orgScoped, setOrgScoped] = React.useState<boolean>(
    Boolean(candidateAdminOrgs.length && defaultOrgId),
  );
  const [submitting, setSubmitting] = React.useState(false);
  const [errMessage, setErrMessage] = React.useState<string | null>(null);

  const trimmedName = name.trim();
  const canSubmit = trimmedName.length > 0 && !submitting;

  const handleSubmit = async (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setErrMessage(null);
    try {
      const body: HamCreateWorkspaceBody = { name: trimmedName };
      if (orgScoped && defaultOrgId) {
        body.org_id = defaultOrgId;
      }
      await onCreate(body);
      // Caller's HamWorkspaceProvider transitions to "ready"; nothing else
      // for this component to do.
    } catch (err) {
      if (err instanceof HamWorkspaceApiError) {
        setErrMessage(err.message);
      } else if (err instanceof Error) {
        setErrMessage(err.message);
      } else {
        setErrMessage("Failed to create workspace");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const wrapperClasses =
    variant === "fullscreen" ? "flex h-full w-full items-center justify-center p-6" : "p-2";

  return (
    <div className={wrapperClasses} data-testid="workspace-onboarding">
      <div className="w-full max-w-md space-y-4 rounded-2xl border border-white/15 bg-[#0b1620] p-6 text-sm text-white/90 shadow-2xl shadow-black/55">
        <div>
          <h2
            id={variant === "dialog" ? "ham-workspace-create-title" : undefined}
            className="text-base font-semibold tracking-tight text-white"
          >
            {variant === "fullscreen" ? "Create your first workspace" : "New workspace"}
          </h2>
          <p className="mt-1 text-white/65">
            A workspace is a tenant boundary for chats, agents, jobs, and artifacts. You can create
            more later.
          </p>
        </div>
        <form className="space-y-3" onSubmit={handleSubmit}>
          <div className="space-y-1.5">
            <Label htmlFor="ham-workspace-name" className="text-white/85">
              Name
            </Label>
            <Input
              id="ham-workspace-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Atlas"
              maxLength={80}
              disabled={submitting}
              required
              className="border-white/20 bg-black/35 text-white placeholder:text-white/40 focus-visible:ring-white/35"
            />
          </div>
          {candidateAdminOrgs.length > 0 ? (
            <div className="flex items-center gap-2 rounded-md border border-white/15 bg-white/[0.06] p-2">
              <input
                id="ham-workspace-org-scoped"
                type="checkbox"
                checked={orgScoped}
                onChange={(e) => setOrgScoped(e.target.checked)}
                disabled={submitting}
                className="h-4 w-4 rounded border-white/30 text-[#ff6b00] focus:ring-white/40"
              />
              <Label htmlFor="ham-workspace-org-scoped" className="text-sm text-white/80">
                Create under{" "}
                <span className="font-medium text-white">
                  {candidateAdminOrgs[0]?.name ?? defaultOrgId}
                </span>
              </Label>
            </div>
          ) : null}
          {errMessage ? (
            <p className="text-xs text-red-300" role="alert">
              {errMessage}
            </p>
          ) : null}
          <div className="flex items-center justify-end gap-2 pt-2">
            {allowDismiss && onDismiss ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onDismiss}
                disabled={submitting}
                className="text-white/80 hover:bg-white/10 hover:text-white"
              >
                Cancel
              </Button>
            ) : null}
            <Button
              type="submit"
              size="sm"
              disabled={!canSubmit}
              className="bg-[#ff6b00] text-black hover:bg-[#ff8533]"
            >
              {submitting ? "Creating…" : "Create workspace"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
