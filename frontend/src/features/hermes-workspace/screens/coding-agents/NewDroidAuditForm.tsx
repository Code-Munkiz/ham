import * as React from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ProjectRecord } from "@/lib/ham/types";
import {
  buildDroidAuditPreviewView,
  validateNewDroidAuditForm,
  type DroidAuditPreview,
  type NewDroidAuditFormInput,
} from "../../adapters/codingAgentsAdapter";
import { previewDroidAudit, launchDroidAudit } from "@/lib/ham/api";
import { CODING_AGENT_LABELS } from "./codingAgentLabels";

interface AuditFormState {
  projectId: string;
  taskPrompt: string;
}

const EMPTY: AuditFormState = { projectId: "", taskPrompt: "" };

type AuditStage = "form" | "preview" | "launching" | "launched";

export function NewDroidAuditForm({
  projects,
  onCancel,
  onLaunched,
}: {
  projects: ProjectRecord[];
  onCancel: () => void;
  onLaunched: (hamRunId: string | null) => void;
}) {
  const [stage, setStage] = React.useState<AuditStage>("form");
  const [form, setForm] = React.useState<AuditFormState>(() => ({
    ...EMPTY,
    projectId: projects.length === 1 ? projects[0]!.id : "",
  }));
  const [errors, setErrors] = React.useState<{ projectId?: string; taskPrompt?: string }>({});
  const [preview, setPreview] = React.useState<DroidAuditPreview | null>(null);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const projectName = React.useMemo(() => {
    const p = projects.find((x) => x.id === form.projectId);
    return p?.name ?? form.projectId;
  }, [projects, form.projectId]);

  async function goPreview() {
    const input: NewDroidAuditFormInput = {
      projectId: form.projectId,
      taskPrompt: form.taskPrompt,
    };
    const v = validateNewDroidAuditForm(input, {
      validationProjectRequired: CODING_AGENT_LABELS.validationProjectRequired,
      validationTaskRequired: CODING_AGENT_LABELS.validationTaskRequired,
    });
    setErrors(v.errors);
    if (!v.ok) return;
    setErrorMessage(null);
    try {
      const payload = await previewDroidAudit({
        project_id: input.projectId,
        user_prompt: input.taskPrompt,
      });
      setPreview(buildDroidAuditPreviewView(payload));
      setStage("preview");
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : String(e));
    }
  }

  async function approve() {
    if (!preview) return;
    setStage("launching");
    setErrorMessage(null);
    try {
      const payload = await launchDroidAudit({
        project_id: form.projectId,
        user_prompt: form.taskPrompt,
        proposal_digest: preview.proposalDigest,
        base_revision: preview.baseRevision,
        confirmed: true,
      });
      if (!payload.ok) {
        setErrorMessage(payload.blocking_reason ?? CODING_AGENT_LABELS.launchFailedToast);
        setStage("preview");
        return;
      }
      setStage("launched");
      onLaunched(payload.ham_run_id ?? null);
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : String(e));
      setStage("preview");
    }
  }

  if (stage === "preview" || stage === "launching") {
    return (
      <PreviewPane
        preview={preview!}
        projectName={projectName}
        busy={stage === "launching"}
        errorMessage={errorMessage}
        onCancel={() => {
          setStage("form");
          setPreview(null);
        }}
        onApprove={() => void approve()}
      />
    );
  }

  if (stage === "launched") {
    return null;
  }

  const inputCls =
    "mt-1 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-sm text-[var(--theme-text)]";
  const errCls = "mt-1 text-[11px] text-amber-300/90";
  const labelCls = "block text-xs font-medium text-[var(--theme-muted)]";

  return (
    <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_16px_48px_var(--theme-shadow)]">
      <div>
        <h2 className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.auditTitle}
        </h2>
        <p className="mt-1 text-xs text-[var(--theme-muted)]">
          {CODING_AGENT_LABELS.auditReadOnlyPill}
        </p>
      </div>

      <label className={labelCls}>
        {CODING_AGENT_LABELS.formProjectLabel}
        <select
          className={inputCls}
          value={form.projectId}
          onChange={(e) => setForm((f) => ({ ...f, projectId: e.target.value }))}
        >
          <option value="">{CODING_AGENT_LABELS.formProjectPlaceholder}</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        {errors.projectId && <span className={errCls}>{errors.projectId}</span>}
      </label>

      <label className={labelCls}>
        {CODING_AGENT_LABELS.auditTaskLabel}
        <textarea
          className={cn(inputCls, "min-h-[140px] resize-y")}
          placeholder={CODING_AGENT_LABELS.auditTaskPlaceholder}
          value={form.taskPrompt}
          onChange={(e) => setForm((f) => ({ ...f, taskPrompt: e.target.value }))}
          maxLength={12_000}
        />
        {errors.taskPrompt && <span className={errCls}>{errors.taskPrompt}</span>}
      </label>

      {errorMessage && <p className="text-xs text-amber-300/90">{errorMessage}</p>}

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {CODING_AGENT_LABELS.cancelCta}
        </Button>
        <Button type="button" size="sm" onClick={() => void goPreview()}>
          {CODING_AGENT_LABELS.previewCta}
        </Button>
      </div>
    </section>
  );
}

function PreviewPane({
  preview,
  projectName,
  busy,
  errorMessage,
  onCancel,
  onApprove,
}: {
  preview: DroidAuditPreview;
  projectName: string;
  busy: boolean;
  errorMessage: string | null;
  onCancel: () => void;
  onApprove: () => void;
}) {
  const Row = ({ k, v }: { k: string; v: string }) => (
    <div className="grid grid-cols-[8rem,1fr] gap-2 text-sm">
      <span className="text-[var(--theme-muted)]">{k}</span>
      <span className="break-words text-[var(--theme-text)]">{v}</span>
    </div>
  );
  return (
    <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_16px_48px_var(--theme-shadow)]">
      <div>
        <h2 className="text-sm font-semibold text-[var(--theme-text)]">
          {CODING_AGENT_LABELS.previewHeading}
        </h2>
        <p className="mt-1 text-xs text-[var(--theme-muted)]">
          {CODING_AGENT_LABELS.auditPreviewIntro}
        </p>
      </div>
      <div className="space-y-2 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
        <Row k={CODING_AGENT_LABELS.formProjectLabel} v={projectName} />
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[var(--theme-muted)]">
            {CODING_AGENT_LABELS.auditTaskLabel}
          </div>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--theme-border)] bg-black/30 p-2 text-[12px] leading-relaxed text-[var(--theme-text)]">
            {preview.taskPromptPreview}
          </pre>
        </div>
        <p className="rounded-md border border-[var(--theme-border)] bg-black/20 px-3 py-2 text-[11px] text-[var(--theme-muted)]">
          {CODING_AGENT_LABELS.auditReadOnlyPill}
        </p>
      </div>
      {errorMessage && <p className="text-xs text-amber-300/90">{errorMessage}</p>}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
          {CODING_AGENT_LABELS.cancelCta}
        </Button>
        <Button type="button" size="sm" onClick={onApprove} disabled={busy}>
          {busy ? "…" : CODING_AGENT_LABELS.approveCta}
        </Button>
      </div>
    </section>
  );
}
