import * as React from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  TASK_KIND_LABELS,
  REVIEW_MODE_LABELS,
  DELETION_POLICY_LABELS,
  EXTERNAL_NETWORK_POLICY_LABELS,
  formatIntentTagsForDisplay,
  type DeletionPolicy,
  type ExternalNetworkPolicy,
  type ModelSource,
  type PermissionPreset,
  type ReviewMode,
  type TaskKind,
} from "./builderStudioLabels";
import { PermissionPresetSelector } from "./PermissionPresetSelector";
import { ModelSourceSelector } from "./ModelSourceSelector";
import {
  adapterErrorMessage,
  builderStudioAdapter,
  type BuilderDraft,
  type BuilderPublic,
} from "../../adapters/builderStudioAdapter";

const TASK_KIND_ORDER: TaskKind[] = [
  "feature",
  "fix",
  "refactor",
  "single_file_edit",
  "multi_file_edit",
  "doc_fix",
  "comments_only",
  "format_only",
  "typo_only",
  "audit",
  "security_review",
  "architecture_report",
  "explain",
];

const REVIEW_MODES: ReviewMode[] = ["always", "on_mutation", "on_delete_only", "never"];
const DELETION_POLICIES: DeletionPolicy[] = ["deny", "require_review", "allow_with_warning"];
const NETWORK_POLICIES: ExternalNetworkPolicy[] = ["deny", "ask", "allow"];

type WizardStep = "identity" | "skill" | "safety" | "model" | "preview";

interface DraftState {
  builder_id: string;
  builder_id_dirty: boolean;
  name: string;
  description: string;
  intent_tags_raw: string;
  task_kinds: TaskKind[];
  permission_preset: PermissionPreset;
  review_mode: ReviewMode;
  deletion_policy: DeletionPolicy;
  external_network_policy: ExternalNetworkPolicy;
  model_source: ModelSource;
  model_ref: string | null;
  show_advanced: boolean;
}

const EMPTY_DRAFT: DraftState = {
  builder_id: "",
  builder_id_dirty: false,
  name: "",
  description: "",
  intent_tags_raw: "",
  task_kinds: ["feature"],
  permission_preset: "app_build",
  review_mode: "on_mutation",
  deletion_policy: "require_review",
  external_network_policy: "deny",
  model_source: "ham_default",
  model_ref: null,
  show_advanced: false,
};

function deriveBuilderId(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function toDraftPayload(workspaceId: string, draft: DraftState): BuilderDraft {
  return {
    builder_id: draft.builder_id.trim(),
    workspace_id: workspaceId,
    name: draft.name.trim(),
    description: draft.description.trim(),
    intent_tags: formatIntentTagsForDisplay(draft.intent_tags_raw.split(",")),
    task_kinds: draft.task_kinds,
    permission_preset: draft.permission_preset,
    allowed_paths: [],
    denied_paths: [],
    denied_operations: [],
    review_mode: draft.review_mode,
    deletion_policy: draft.deletion_policy,
    external_network_policy: draft.external_network_policy,
    model_source: draft.model_source,
    model_ref: draft.model_ref?.trim() ? draft.model_ref.trim() : null,
    enabled: true,
  };
}

export function CreateBuilderWizard({
  workspaceId,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  onClose: () => void;
  onCreated: (builder: BuilderPublic) => void;
}) {
  const [step, setStep] = React.useState<WizardStep>("identity");
  const [draft, setDraft] = React.useState<DraftState>(EMPTY_DRAFT);
  const [previewSummary, setPreviewSummary] = React.useState<string | null>(null);
  const [previewError, setPreviewError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const update = (patch: Partial<DraftState>) => setDraft((d) => ({ ...d, ...patch }));

  const setName = (next: string) => {
    setDraft((d) => ({
      ...d,
      name: next,
      builder_id: d.builder_id_dirty ? d.builder_id : deriveBuilderId(next),
    }));
  };

  const toggleTaskKind = (kind: TaskKind) => {
    setDraft((d) => {
      const has = d.task_kinds.includes(kind);
      return {
        ...d,
        task_kinds: has ? d.task_kinds.filter((k) => k !== kind) : [...d.task_kinds, kind],
      };
    });
  };

  const canAdvanceFromIdentity = Boolean(draft.name.trim()) && Boolean(draft.builder_id.trim());
  const canAdvanceFromSkill = draft.task_kinds.length > 0;

  const handlePreview = async () => {
    setSubmitting(true);
    setPreviewError(null);
    const result = await builderStudioAdapter.preview(
      workspaceId,
      toDraftPayload(workspaceId, draft),
    );
    setSubmitting(false);
    if (result.error) {
      setPreviewError(adapterErrorMessage(result.error));
      setPreviewSummary(null);
      return;
    }
    setPreviewSummary(result.summary ?? "Builder is ready to save.");
    setStep("preview");
  };

  const handleSave = async () => {
    setSubmitting(true);
    setPreviewError(null);
    const result = await builderStudioAdapter.create(
      workspaceId,
      toDraftPayload(workspaceId, draft),
    );
    setSubmitting(false);
    if (result.error || !result.builder) {
      const msg = result.error ? adapterErrorMessage(result.error) : "Couldn't save the builder.";
      setPreviewError(msg);
      toast.error(msg, { duration: 6000 });
      return;
    }
    toast.success("Builder saved.", { duration: 4000 });
    onCreated(result.builder);
  };

  const labelCls = "block text-xs font-medium text-[var(--theme-muted)]";
  const inputCls =
    "mt-1 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-sm text-[var(--theme-text)]";

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--theme-bg)] shadow-2xl"
        style={{ color: "var(--theme-text)" }}
      >
        <div className="flex items-start justify-between gap-2 border-b border-white/10 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold">Create a builder</h2>
            <p className="mt-0.5 text-xs text-[var(--theme-muted)]">Step {stepIndex(step)} of 4</p>
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {step === "identity" ? (
            <section className="space-y-3">
              <label className={labelCls}>
                Builder name
                <input
                  type="text"
                  className={inputCls}
                  value={draft.name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Game Builder"
                  maxLength={80}
                />
              </label>
              <label className={labelCls}>
                Builder id
                <input
                  type="text"
                  className={inputCls}
                  value={draft.builder_id}
                  onChange={(e) => update({ builder_id: e.target.value, builder_id_dirty: true })}
                  placeholder="game-builder"
                  maxLength={64}
                  spellCheck={false}
                  autoComplete="off"
                />
                <span className="mt-1 block text-[10px] text-[var(--theme-muted)]">
                  Lowercase letters, numbers, dashes, and underscores only.
                </span>
              </label>
              <label className={labelCls}>
                What it&apos;s good at
                <textarea
                  className={inputCls + " min-h-[100px] resize-y"}
                  value={draft.description}
                  onChange={(e) => update({ description: e.target.value })}
                  placeholder="A builder that helps me ship small 2D games."
                  maxLength={2000}
                />
              </label>
              <label className={labelCls}>
                Intent tags (comma-separated)
                <input
                  type="text"
                  className={inputCls}
                  value={draft.intent_tags_raw}
                  onChange={(e) => update({ intent_tags_raw: e.target.value })}
                  placeholder="games, phaser, ui"
                />
              </label>
            </section>
          ) : null}

          {step === "skill" ? (
            <section className="space-y-3">
              <p className="text-xs text-[var(--theme-muted)]">
                Pick the kinds of tasks HAM should consider this builder for.
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {TASK_KIND_ORDER.map((kind) => {
                  const checked = draft.task_kinds.includes(kind);
                  return (
                    <label
                      key={kind}
                      className="flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTaskKind(kind)}
                        className="h-3.5 w-3.5 accent-[var(--theme-accent)]"
                      />
                      <span className="text-sm text-[var(--theme-text)]">
                        {TASK_KIND_LABELS[kind]}
                      </span>
                    </label>
                  );
                })}
              </div>
            </section>
          ) : null}

          {step === "safety" ? (
            <section className="space-y-4">
              <PermissionPresetSelector
                value={draft.permission_preset}
                onChange={(next) => update({ permission_preset: next })}
                showAdvanced={draft.show_advanced}
              />
              <label className="flex items-center gap-2 text-[11px] text-[var(--theme-muted)]">
                <input
                  type="checkbox"
                  checked={draft.show_advanced}
                  onChange={(e) => update({ show_advanced: e.target.checked })}
                  className="h-3.5 w-3.5 accent-[var(--theme-accent)]"
                />
                Show advanced safety options
              </label>

              <RadioGroup
                legend="Review behavior"
                values={REVIEW_MODES}
                labels={REVIEW_MODE_LABELS}
                value={draft.review_mode}
                onChange={(v) => update({ review_mode: v })}
              />

              <RadioGroup
                legend="Deletion policy"
                values={DELETION_POLICIES}
                labels={DELETION_POLICY_LABELS}
                value={draft.deletion_policy}
                onChange={(v) => update({ deletion_policy: v })}
              />

              <RadioGroup
                legend="Internet access"
                values={NETWORK_POLICIES}
                labels={EXTERNAL_NETWORK_POLICY_LABELS}
                value={draft.external_network_policy}
                onChange={(v) => update({ external_network_policy: v })}
              />
            </section>
          ) : null}

          {step === "model" ? (
            <section className="space-y-3">
              <ModelSourceSelector
                value={draft.model_source}
                modelRef={draft.model_ref}
                onChange={(next) => update({ model_source: next })}
                onModelRefChange={(next) => update({ model_ref: next })}
              />
            </section>
          ) : null}

          {step === "preview" ? (
            <section className="space-y-3 text-sm">
              <h3 className="text-sm font-semibold text-[var(--theme-text)]">Ready to save</h3>
              <p className="text-xs text-[var(--theme-muted)]">
                Review what HAM will remember about this builder.
              </p>
              {previewSummary ? (
                <div className="rounded-xl border border-emerald-300/30 bg-emerald-300/[0.04] p-3 text-xs text-[var(--theme-text)]">
                  {previewSummary}
                </div>
              ) : null}
              <dl className="grid gap-2 text-xs text-[var(--theme-muted)]">
                <Row k="Name" v={draft.name} />
                <Row k="Id" v={draft.builder_id} />
                <Row k="Description" v={draft.description || "—"} />
                <Row
                  k="Tags"
                  v={formatIntentTagsForDisplay(draft.intent_tags_raw.split(",")).join(", ") || "—"}
                />
                <Row
                  k="Task kinds"
                  v={draft.task_kinds.map((k) => TASK_KIND_LABELS[k]).join(", ")}
                />
                <Row k="Safety" v={draft.permission_preset} />
                <Row k="Review" v={REVIEW_MODE_LABELS[draft.review_mode]} />
                <Row k="Deletion" v={DELETION_POLICY_LABELS[draft.deletion_policy]} />
                <Row
                  k="Network"
                  v={EXTERNAL_NETWORK_POLICY_LABELS[draft.external_network_policy]}
                />
                <Row k="Model" v={draft.model_source} />
              </dl>
            </section>
          ) : null}

          {previewError ? (
            <p className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-100/90">
              {previewError}
            </p>
          ) : null}
        </div>

        <WizardFooter
          step={step}
          submitting={submitting}
          canAdvanceFromIdentity={canAdvanceFromIdentity}
          canAdvanceFromSkill={canAdvanceFromSkill}
          onBack={() => setStep(prevStep(step))}
          onNext={() => setStep(nextStep(step))}
          onPreview={handlePreview}
          onSave={handleSave}
        />
      </div>
    </div>
  );
}

function WizardFooter({
  step,
  submitting,
  canAdvanceFromIdentity,
  canAdvanceFromSkill,
  onBack,
  onNext,
  onPreview,
  onSave,
}: {
  step: WizardStep;
  submitting: boolean;
  canAdvanceFromIdentity: boolean;
  canAdvanceFromSkill: boolean;
  onBack: () => void;
  onNext: () => void;
  onPreview: () => void;
  onSave: () => void;
}) {
  const backDisabled = step === "identity";
  let nextDisabled = false;
  if (step === "identity") nextDisabled = !canAdvanceFromIdentity;
  if (step === "skill") nextDisabled = !canAdvanceFromSkill;

  return (
    <div className="flex items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
      <Button type="button" size="sm" variant="ghost" onClick={onBack} disabled={backDisabled}>
        Back
      </Button>
      {step === "model" ? (
        <Button type="button" size="sm" onClick={onPreview} disabled={submitting}>
          {submitting ? "Preparing…" : "Preview"}
        </Button>
      ) : step === "preview" ? (
        <Button type="button" size="sm" onClick={onSave} disabled={submitting}>
          {submitting ? "Saving…" : "Save builder"}
        </Button>
      ) : (
        <Button type="button" size="sm" onClick={onNext} disabled={nextDisabled}>
          Next
        </Button>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[6rem,1fr] gap-2">
      <dt className="text-[var(--theme-muted)]">{k}</dt>
      <dd className="break-words text-[var(--theme-text)]">{v}</dd>
    </div>
  );
}

function RadioGroup<T extends string>({
  legend,
  values,
  labels,
  value,
  onChange,
}: {
  legend: string;
  values: T[];
  labels: Record<T, string>;
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <fieldset className="space-y-1">
      <legend className="text-xs font-medium text-[var(--theme-muted)]">{legend}</legend>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {values.map((v) => (
          <label
            key={v}
            className="flex cursor-pointer items-center gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-1.5 text-xs"
          >
            <input
              type="radio"
              checked={value === v}
              onChange={() => onChange(v)}
              className="h-3.5 w-3.5 accent-[var(--theme-accent)]"
            />
            <span className="text-[var(--theme-text)]">{labels[v]}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function stepIndex(step: WizardStep): number {
  switch (step) {
    case "identity":
      return 1;
    case "skill":
      return 2;
    case "safety":
      return 3;
    case "model":
      return 4;
    default:
      return 4;
  }
}

function nextStep(step: WizardStep): WizardStep {
  switch (step) {
    case "identity":
      return "skill";
    case "skill":
      return "safety";
    case "safety":
      return "model";
    case "model":
      return "preview";
    default:
      return "preview";
  }
}

function prevStep(step: WizardStep): WizardStep {
  switch (step) {
    case "skill":
      return "identity";
    case "safety":
      return "skill";
    case "model":
      return "safety";
    case "preview":
      return "model";
    default:
      return "identity";
  }
}
