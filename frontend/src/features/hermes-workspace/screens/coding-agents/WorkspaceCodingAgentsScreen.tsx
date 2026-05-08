import * as React from "react";
import { Link } from "react-router-dom";
import { Bot, Plus, RefreshCw, ScanLine } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listHamProjects } from "@/lib/ham/api";
import type { ProjectRecord } from "@/lib/ham/types";
import {
  WorkspaceSurfaceHeader,
  WorkspaceSurfaceStateCard,
} from "../../components/workspaceSurfaceChrome";
import {
  buildPreview,
  fetchCursorReadiness,
  launchNewCodingTask,
  validateNewCodingTaskForm,
  type CodingAgentReadiness,
  type CodingTaskPreview,
  type NewCodingTaskFormInput,
} from "../../adapters/codingAgentsAdapter";
import { CodingAgentReadinessPill } from "./CodingAgentReadinessPill";
import { CodingAgentChooser, type CodingAgentLane } from "./CodingAgentChooser";
import { NewDroidAuditForm } from "./NewDroidAuditForm";
import { CodingAgentRunsList } from "./CodingAgentRunsList";
import { CODING_AGENT_LABELS } from "./codingAgentLabels";

type Stage = "idle" | "chooser" | "form" | "preview" | "launching" | "launched" | "audit";

interface FormState {
  projectId: string;
  repository: string;
  taskPrompt: string;
  ref: string;
  branchName: string;
  autoCreatePr: boolean;
}

const EMPTY_FORM: FormState = {
  projectId: "",
  repository: "",
  taskPrompt: "",
  ref: "",
  branchName: "",
  autoCreatePr: false,
};

function toAdapterInput(f: FormState): NewCodingTaskFormInput {
  return {
    projectId: f.projectId,
    repository: f.repository,
    taskPrompt: f.taskPrompt,
    ref: f.ref,
    branchName: f.branchName,
    autoCreatePr: f.autoCreatePr,
  };
}

export function WorkspaceCodingAgentsScreen() {
  const [stage, setStage] = React.useState<Stage>("idle");
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = React.useState<{
    projectId?: string;
    repository?: string;
    taskPrompt?: string;
  }>({});

  const [readiness, setReadiness] = React.useState<CodingAgentReadiness>("needs_setup");
  const [readinessError, setReadinessError] = React.useState<string | null>(null);
  const [readinessLoading, setReadinessLoading] = React.useState(true);

  const [projects, setProjects] = React.useState<ProjectRecord[]>([]);
  const [projectsError, setProjectsError] = React.useState<string | null>(null);

  const [preview, setPreview] = React.useState<CodingTaskPreview | null>(null);
  const [launchedAgentId, setLaunchedAgentId] = React.useState<string | null>(null);
  const [auditRunsRefreshKey, setAuditRunsRefreshKey] = React.useState(0);
  const [auditProjectId, setAuditProjectId] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setReadinessLoading(true);
    setReadinessError(null);
    setProjectsError(null);
    const [r, p] = await Promise.all([
      fetchCursorReadiness(),
      listHamProjects().catch((e: unknown) => ({
        projects: [] as ProjectRecord[],
        _error: e instanceof Error ? e.message : String(e),
      })),
    ]);
    setReadiness(r.readiness);
    if (r.error) setReadinessError(r.error);
    if ("_error" in p && p._error) {
      setProjectsError(p._error);
      setProjects([]);
    } else {
      setProjects(p.projects);
      setAuditProjectId((current) => {
        if (current && p.projects.some((proj) => proj.id === current)) {
          return current;
        }
        return p.projects[0]?.id ?? null;
      });
    }
    setReadinessLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const droidReady = projects.length > 0;
  const cursorLaunchable = readiness === "ready" && projects.length > 0;
  const showChooser = cursorLaunchable && droidReady;

  const startNewTask = () => {
    setForm({
      ...EMPTY_FORM,
      projectId: projects.length === 1 ? projects[0]!.id : "",
    });
    setErrors({});
    setPreview(null);
    setLaunchedAgentId(null);
    if (showChooser) {
      setStage("chooser");
      return;
    }
    if (cursorLaunchable) {
      setStage("form");
      return;
    }
    if (droidReady) {
      setStage("audit");
      return;
    }
  };

  const pickLane = (next: CodingAgentLane) => {
    setStage(next === "cursor" ? "form" : "audit");
  };

  const cancel = () => {
    setStage("idle");
    setForm(EMPTY_FORM);
    setErrors({});
    setPreview(null);
  };

  const goPreview = () => {
    const input = toAdapterInput(form);
    const v = validateNewCodingTaskForm(input, {
      validationProjectRequired: CODING_AGENT_LABELS.validationProjectRequired,
      validationRepositoryRequired: CODING_AGENT_LABELS.validationRepositoryRequired,
      validationTaskRequired: CODING_AGENT_LABELS.validationTaskRequired,
    });
    setErrors(v.errors);
    if (!v.ok) return;
    setPreview(buildPreview(input));
    setStage("preview");
  };

  const approve = async () => {
    setStage("launching");
    const out = await launchNewCodingTask(toAdapterInput(form));
    if (!out.ok) {
      toast.error(CODING_AGENT_LABELS.launchFailedToast, { duration: 8_000 });
      if (out.errorMessage) toast.error(out.errorMessage, { duration: 10_000 });
      setStage("preview");
      return;
    }
    setLaunchedAgentId(out.cursorAgentId);
    toast.success(CODING_AGENT_LABELS.launchedToast, { duration: 6_000 });
    setStage("launched");
  };

  const launchDisabled = readinessLoading || projects.length === 0;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col gap-3 p-3 md:p-4">
      <WorkspaceSurfaceHeader
        eyebrow="Workspace"
        title={CODING_AGENT_LABELS.surfaceTitle}
        subtitle={CODING_AGENT_LABELS.surfaceSubtitle}
        actions={
          <>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => void refresh()}
              disabled={readinessLoading}
              className="h-8 gap-1"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", readinessLoading && "animate-spin")} />
              Refresh
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={startNewTask}
              disabled={launchDisabled}
              className="h-8 gap-1"
            >
              <Plus className="h-3.5 w-3.5" />
              {CODING_AGENT_LABELS.newTaskCta}
            </Button>
          </>
        }
      />

      <ProviderRow
        readiness={readiness}
        readinessError={readinessError}
        readinessLoading={readinessLoading}
        droidReady={droidReady}
      />

      {projectsError && (
        <WorkspaceSurfaceStateCard
          title="Couldn't load your projects"
          description="Retry, or open Settings to register a project."
          tone="amber"
          technicalDetail={projectsError}
          primaryAction={
            <Button type="button" size="sm" variant="secondary" onClick={() => void refresh()}>
              Retry
            </Button>
          }
        />
      )}

      {!readinessLoading && readiness !== "ready" && !droidReady && (
        <WorkspaceSurfaceStateCard
          title={CODING_AGENT_LABELS.setupNeededTitle}
          description={CODING_AGENT_LABELS.setupNeededBody}
          tone="amber"
          primaryAction={
            <Button type="button" size="sm" variant="secondary" asChild>
              <Link to="/workspace/settings">{CODING_AGENT_LABELS.setupNeededOpenSettings}</Link>
            </Button>
          }
        />
      )}

      {!readinessLoading && readiness === "ready" && projects.length === 0 && !projectsError && (
        <WorkspaceSurfaceStateCard
          title={CODING_AGENT_LABELS.noProjectsTitle}
          description={CODING_AGENT_LABELS.noProjectsBody}
          tone="amber"
          primaryAction={
            <Button type="button" size="sm" variant="secondary" asChild>
              <Link to="/workspace/settings">{CODING_AGENT_LABELS.setupNeededOpenSettings}</Link>
            </Button>
          }
        />
      )}

      {stage === "chooser" && (
        <CodingAgentChooser
          cursorReady={cursorLaunchable}
          droidReady={droidReady}
          onPick={pickLane}
          onCancel={cancel}
        />
      )}

      {stage === "audit" && (
        <NewDroidAuditForm
          projects={projects}
          onCancel={cancel}
          onLaunched={(_hamRunId) => {
            toast.success(CODING_AGENT_LABELS.auditLaunchedToast, { duration: 6_000 });
            setAuditProjectId(form.projectId || null);
            setAuditRunsRefreshKey((k) => k + 1);
            setStage("idle");
          }}
        />
      )}

      {stage === "form" && (
        <NewTaskForm
          form={form}
          setForm={setForm}
          errors={errors}
          projects={projects}
          onCancel={cancel}
          onPreview={goPreview}
        />
      )}

      {stage === "preview" && preview && (
        <PreviewPane
          preview={preview}
          projectName={projects.find((p) => p.id === preview.projectId)?.name ?? preview.projectId}
          onCancel={cancel}
          onApprove={() => void approve()}
          busy={false}
        />
      )}

      {stage === "launching" && preview && (
        <PreviewPane
          preview={preview}
          projectName={projects.find((p) => p.id === preview.projectId)?.name ?? preview.projectId}
          onCancel={cancel}
          onApprove={() => void approve()}
          busy
        />
      )}

      {stage === "launched" && (
        <WorkspaceSurfaceStateCard
          title={CODING_AGENT_LABELS.launchedToast}
          description={
            launchedAgentId
              ? "Your task is running. Open Operations to follow live progress."
              : "Your task was sent. Open Operations to follow live progress."
          }
          primaryAction={
            <Button type="button" size="sm" variant="secondary" asChild>
              <Link to="/workspace/operations">{CODING_AGENT_LABELS.trackProgressCta}</Link>
            </Button>
          }
          secondaryAction={
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setStage("idle");
                setForm(EMPTY_FORM);
                setPreview(null);
                setLaunchedAgentId(null);
              }}
            >
              {CODING_AGENT_LABELS.newTaskCta}
            </Button>
          }
        />
      )}

      {stage === "idle" && projects.length > 0 && (cursorLaunchable || droidReady) && (
        <IdleHero onStart={startNewTask} />
      )}

      {droidReady && (stage === "idle" || stage === "launched") && (
        <CodingAgentRunsList projectId={auditProjectId} refreshKey={auditRunsRefreshKey} />
      )}

      <p className="mt-auto text-[10px] leading-relaxed text-[var(--theme-muted)]">
        {CODING_AGENT_LABELS.comingSoonNote}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function ProviderRow({
  readiness,
  readinessError,
  readinessLoading,
  droidReady,
}: {
  readiness: CodingAgentReadiness;
  readinessError: string | null;
  readinessLoading: boolean;
  droidReady: boolean;
}) {
  return (
    <section className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] px-4 py-3 shadow-[0_12px_40px_var(--theme-shadow)]">
      <div className="flex items-center gap-2">
        <Bot className="h-4 w-4 text-[var(--theme-accent)]" />
        <span className="text-sm font-semibold text-[var(--theme-text)]">Cursor</span>
        {readinessLoading ? (
          <span className="text-[10px] uppercase tracking-wider text-[var(--theme-muted)]">
            Checking…
          </span>
        ) : (
          <CodingAgentReadinessPill readiness={readiness} />
        )}
      </div>
      <span className="text-[var(--theme-muted)]">·</span>
      <div className="flex items-center gap-2">
        <ScanLine className="h-4 w-4 text-[var(--theme-accent)]" />
        <span className="text-sm font-semibold text-[var(--theme-text)]">Factory Droid</span>
        <CodingAgentReadinessPill readiness={droidReady ? "ready" : "needs_setup"} />
      </div>
      {readinessError && <span className="text-[11px] text-amber-300/80">{readinessError}</span>}
    </section>
  );
}

function IdleHero({ onStart }: { onStart: () => void }) {
  return (
    <section className="rounded-2xl border border-dashed border-[var(--theme-border)] bg-[var(--theme-bg)] px-6 py-10 text-center shadow-[0_12px_40px_var(--theme-shadow)]">
      <Bot className="mx-auto h-8 w-8 text-[var(--theme-accent)]" />
      <h2 className="mt-3 text-base font-semibold text-[var(--theme-text)]">
        {CODING_AGENT_LABELS.surfaceTitle}
      </h2>
      <p className="mt-1 text-sm text-[var(--theme-muted)]">
        {CODING_AGENT_LABELS.surfaceSubtitle}
      </p>
      <Button type="button" size="sm" className="mt-4 gap-1" onClick={onStart}>
        <Plus className="h-3.5 w-3.5" />
        {CODING_AGENT_LABELS.newTaskCta}
      </Button>
    </section>
  );
}

function NewTaskForm({
  form,
  setForm,
  errors,
  projects,
  onCancel,
  onPreview,
}: {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
  errors: { projectId?: string; repository?: string; taskPrompt?: string };
  projects: ProjectRecord[];
  onCancel: () => void;
  onPreview: () => void;
}) {
  const inputCls =
    "mt-1 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-sm text-[var(--theme-text)]";
  const errCls = "mt-1 text-[11px] text-amber-300/90";
  const labelCls = "block text-xs font-medium text-[var(--theme-muted)]";
  return (
    <section className="space-y-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-card)] p-4 shadow-[0_16px_48px_var(--theme-shadow)]">
      <h2 className="text-sm font-semibold text-[var(--theme-text)]">
        {CODING_AGENT_LABELS.newTaskCta}
      </h2>

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
        {CODING_AGENT_LABELS.formRepositoryLabel}
        <input
          className={inputCls}
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder={CODING_AGENT_LABELS.formRepositoryPlaceholder}
          value={form.repository}
          onChange={(e) => setForm((f) => ({ ...f, repository: e.target.value }))}
        />
        {errors.repository && <span className={errCls}>{errors.repository}</span>}
      </label>

      <label className={labelCls}>
        {CODING_AGENT_LABELS.formTaskLabel}
        <textarea
          className={cn(inputCls, "min-h-[120px] resize-y")}
          placeholder={CODING_AGENT_LABELS.formTaskPlaceholder}
          value={form.taskPrompt}
          onChange={(e) => setForm((f) => ({ ...f, taskPrompt: e.target.value }))}
          maxLength={100_000}
        />
        {errors.taskPrompt && <span className={errCls}>{errors.taskPrompt}</span>}
      </label>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className={labelCls}>
          {CODING_AGENT_LABELS.formBranchLabel}
          <input
            className={inputCls}
            placeholder="main"
            value={form.ref}
            onChange={(e) => setForm((f) => ({ ...f, ref: e.target.value }))}
          />
        </label>
        <label className={labelCls}>
          {CODING_AGENT_LABELS.formBranchNamePrLabel}
          <input
            className={inputCls}
            placeholder="feat/your-change"
            value={form.branchName}
            onChange={(e) => setForm((f) => ({ ...f, branchName: e.target.value }))}
          />
        </label>
      </div>

      <label className="flex items-center gap-2 text-xs text-[var(--theme-text)]">
        <input
          type="checkbox"
          checked={form.autoCreatePr}
          onChange={(e) => setForm((f) => ({ ...f, autoCreatePr: e.target.checked }))}
        />
        {CODING_AGENT_LABELS.formAutoCreatePrLabel}
      </label>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          {CODING_AGENT_LABELS.cancelCta}
        </Button>
        <Button type="button" size="sm" onClick={onPreview}>
          {CODING_AGENT_LABELS.previewCta}
        </Button>
      </div>
    </section>
  );
}

function PreviewPane({
  preview,
  projectName,
  onCancel,
  onApprove,
  busy,
}: {
  preview: CodingTaskPreview;
  projectName: string;
  onCancel: () => void;
  onApprove: () => void;
  busy: boolean;
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
        <p className="mt-1 text-xs text-[var(--theme-muted)]">{CODING_AGENT_LABELS.previewIntro}</p>
      </div>
      <div className="space-y-2 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-3">
        <Row k={CODING_AGENT_LABELS.formProjectLabel} v={projectName} />
        <Row k={CODING_AGENT_LABELS.formRepositoryLabel} v={preview.repository} />
        {preview.ref && <Row k={CODING_AGENT_LABELS.formBranchLabel} v={preview.ref} />}
        {preview.branchName && (
          <Row k={CODING_AGENT_LABELS.formBranchNamePrLabel} v={preview.branchName} />
        )}
        <Row
          k={CODING_AGENT_LABELS.formAutoCreatePrLabel}
          v={preview.autoCreatePr ? "Yes" : "No"}
        />
        <div>
          <div className="text-[11px] uppercase tracking-wider text-[var(--theme-muted)]">
            {CODING_AGENT_LABELS.formTaskLabel}
          </div>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-[var(--theme-border)] bg-black/30 p-2 text-[12px] leading-relaxed text-[var(--theme-text)]">
            {preview.taskPromptPreview}
          </pre>
        </div>
      </div>
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
