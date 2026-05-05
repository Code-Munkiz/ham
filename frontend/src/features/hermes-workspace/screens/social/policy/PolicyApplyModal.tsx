import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { APPLY_CONFIRMATION_PHRASE } from "./lib/policyConstants";
import { UI_TEXT, labelForError } from "./lib/policyCopy";
import type {
  SocialPolicyApplyResponse,
  SocialPolicyPreviewResponse,
  SocialPolicyServerError,
} from "./lib/policyTypes";

export type ApplyState =
  | { kind: "idle" }
  | { kind: "applying" }
  | { kind: "success"; result: SocialPolicyApplyResponse }
  | { kind: "revision_conflict"; error: SocialPolicyServerError }
  | { kind: "error"; error: SocialPolicyServerError };

export interface PolicyApplyModalProps {
  open: boolean;
  preview: SocialPolicyPreviewResponse;
  writesEnabled: boolean;
  state: ApplyState;
  onApply: (input: { confirmationPhrase: string; writeToken: string }) => void;
  onClose: () => void;
  onReloadAndKeepEdits?: () => void;
}

export function PolicyApplyModal({
  open,
  preview,
  writesEnabled,
  state,
  onApply,
  onClose,
  onReloadAndKeepEdits,
}: PolicyApplyModalProps): React.ReactElement | null {
  const [phrase, setPhrase] = React.useState("");
  const [token, setToken] = React.useState("");

  React.useEffect(() => {
    if (!open) {
      setPhrase("");
      setToken("");
    }
  }, [open]);

  if (!open) return null;

  const phraseOk = phrase.trim() === APPLY_CONFIRMATION_PHRASE;
  const tokenOk = token.trim().length > 0;
  const liveOk = preview.live_autonomy_change === false;
  const noLocalConflict = state.kind !== "revision_conflict";
  const checklist = [
    { ok: writesEnabled, label: "Writes enabled on server" },
    { ok: liveOk, label: "No live-autonomy change in diff" },
    { ok: noLocalConflict, label: "No revision conflict" },
    { ok: preview.diff.length > 0, label: "Diff is non-empty" },
  ];
  const checklistOk = checklist.every((c) => c.ok);

  const isApplying = state.kind === "applying";
  const canSubmit = checklistOk && phraseOk && tokenOk && !isApplying;

  const errEnvelope =
    state.kind === "revision_conflict" || state.kind === "error" ? state.error : null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="policy-apply-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    >
      <div className="w-full max-w-lg rounded-xl border border-border bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border/40 p-4">
          <h2 id="policy-apply-modal-title" className="text-lg font-semibold">
            {state.kind === "success"
              ? UI_TEXT.applySuccessTitle
              : state.kind === "revision_conflict"
                ? UI_TEXT.applyConflictTitle
                : UI_TEXT.applyButton}
          </h2>
          <button
            type="button"
            aria-label={UI_TEXT.closeButton}
            className="text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {state.kind === "success" ? (
          <div className="flex flex-col gap-3 p-4 text-sm">
            <p className="text-green-600">Policy saved successfully.</p>
            <p>
              {UI_TEXT.applySuccessNewRevision}:{" "}
              <code className="text-xs">{state.result.new_revision.slice(0, 16)}…</code>
            </p>
            <p className="text-xs text-muted-foreground">
              audit_id: {state.result.audit_id} · backup_id: {state.result.backup_id}
            </p>
            <div className="mt-2 flex justify-end">
              <Button onClick={onClose}>{UI_TEXT.closeButton}</Button>
            </div>
          </div>
        ) : state.kind === "revision_conflict" ? (
          <div className="flex flex-col gap-3 p-4 text-sm">
            <p>{UI_TEXT.applyConflictBody}</p>
            <div className="rounded-md border border-border/40 bg-muted/30 p-2 text-xs">
              {labelForError(state.error)}
            </div>
            <div className="mt-2 flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>
                {UI_TEXT.cancelButton}
              </Button>
              {onReloadAndKeepEdits ? (
                <Button onClick={onReloadAndKeepEdits}>
                  {UI_TEXT.reloadAndKeepEdits}
                </Button>
              ) : null}
            </div>
          </div>
        ) : (
          <form
            className="flex flex-col gap-4 p-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!canSubmit) return;
              onApply({ confirmationPhrase: phrase.trim(), writeToken: token.trim() });
            }}
          >
            <section>
              <p className="mb-2 text-sm font-medium">{UI_TEXT.applyChecklistTitle}</p>
              <ul className="space-y-1 text-xs">
                {checklist.map((c) => (
                  <li key={c.label} className="flex items-center gap-2">
                    <span
                      className={
                        c.ok ? "text-green-600" : "text-destructive"
                      }
                    >
                      {c.ok ? "✓" : "✗"}
                    </span>
                    <span>{c.label}</span>
                  </li>
                ))}
              </ul>
            </section>

            <div className="rounded-md border border-border/40 bg-muted/20 p-2 text-xs">
              <p className="font-medium">Diff summary</p>
              <p className="text-muted-foreground">
                {preview.diff.length} change(s) · base {preview.base_revision.slice(0, 12)}…
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="apply__phrase">{UI_TEXT.applyPhraseLabel}</Label>
              <Input
                id="apply__phrase"
                type="text"
                autoComplete="off"
                value={phrase}
                onChange={(e) => setPhrase(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Type exactly: <code>{APPLY_CONFIRMATION_PHRASE}</code>
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="apply__token">{UI_TEXT.applyTokenLabel}</Label>
              <Input
                id="apply__token"
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{UI_TEXT.applyTokenHelp}</p>
            </div>

            {errEnvelope && state.kind === "error" ? (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {labelForError(errEnvelope)}
              </div>
            ) : null}

            <div className="flex items-center justify-end gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                {UI_TEXT.cancelButton}
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {isApplying ? "Saving…" : UI_TEXT.applyButton}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
