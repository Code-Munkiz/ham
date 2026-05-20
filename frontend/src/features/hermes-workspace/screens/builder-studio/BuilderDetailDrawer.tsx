import * as React from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  builderStudioAdapter,
  adapterErrorMessage,
  type BuilderPublic,
} from "../../adapters/builderStudioAdapter";
import {
  DELETION_POLICY_LABELS,
  EXTERNAL_NETWORK_POLICY_LABELS,
  MODEL_SOURCE_LABELS,
  PERMISSION_PRESET_LABELS,
  REVIEW_MODE_LABELS,
  TASK_KIND_LABELS,
  formatIntentTagsForDisplay,
  type DeletionPolicy,
  type ExternalNetworkPolicy,
  type ModelSource,
  type PermissionPreset,
  type ReviewMode,
  type TaskKind,
} from "./builderStudioLabels";

export function BuilderDetailDrawer({
  builder,
  workspaceId,
  isOperator,
  onClose,
  onChanged,
  onOpenTechnical,
}: {
  builder: BuilderPublic;
  workspaceId: string;
  isOperator: boolean;
  onClose: () => void;
  onChanged: () => void;
  onOpenTechnical: () => void;
}) {
  const [confirmingDisable, setConfirmingDisable] = React.useState(false);
  const [pending, setPending] = React.useState(false);
  const tags = formatIntentTagsForDisplay(builder.intent_tags ?? []);

  const handleDisable = async () => {
    setPending(true);
    const result = await builderStudioAdapter.softDelete(workspaceId, builder.builder_id);
    setPending(false);
    if (!result.ok) {
      const msg = result.error ? adapterErrorMessage(result.error) : "Couldn't disable builder.";
      toast.error(msg, { duration: 6000 });
      return;
    }
    toast.success("Builder disabled.", { duration: 4000 });
    setConfirmingDisable(false);
    onChanged();
    onClose();
  };

  const handleToggleEnabled = async () => {
    setPending(true);
    const result = await builderStudioAdapter.update(workspaceId, builder.builder_id, {
      enabled: !builder.enabled,
    });
    setPending(false);
    if (result.error || !result.builder) {
      const msg = result.error ? adapterErrorMessage(result.error) : "Couldn't update builder.";
      toast.error(msg, { duration: 6000 });
      return;
    }
    toast.success(result.builder.enabled ? "Builder enabled." : "Builder disabled.", {
      duration: 4000,
    });
    onChanged();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--theme-bg)] shadow-2xl"
        style={{ color: "var(--theme-text)" }}
      >
        <div className="flex items-start justify-between gap-2 border-b border-white/10 px-5 py-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold">{builder.name}</h2>
            <p className="mt-0.5 font-mono text-[10px] text-[var(--theme-muted)]">
              {builder.builder_id}
            </p>
          </div>
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4 text-sm">
          <p className="whitespace-pre-wrap text-[var(--theme-text)]">
            {builder.description || "—"}
          </p>

          {tags.length ? (
            <div className="flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full border border-white/15 bg-white/[0.04] px-2 py-0.5 text-[10px] text-white/70"
                >
                  {t}
                </span>
              ))}
            </div>
          ) : null}

          <dl className="grid gap-2 text-xs text-[var(--theme-muted)]">
            <DRow
              k="Safety"
              v={
                PERMISSION_PRESET_LABELS[builder.permission_preset as PermissionPreset] ??
                builder.permission_preset
              }
            />
            <DRow
              k="Review"
              v={REVIEW_MODE_LABELS[builder.review_mode as ReviewMode] ?? builder.review_mode}
            />
            <DRow
              k="Deletion"
              v={
                DELETION_POLICY_LABELS[builder.deletion_policy as DeletionPolicy] ??
                builder.deletion_policy
              }
            />
            <DRow
              k="Network"
              v={
                EXTERNAL_NETWORK_POLICY_LABELS[
                  builder.external_network_policy as ExternalNetworkPolicy
                ] ?? builder.external_network_policy
              }
            />
            <DRow
              k="Model"
              v={MODEL_SOURCE_LABELS[builder.model_source as ModelSource] ?? builder.model_source}
            />
            <DRow
              k="Tasks"
              v={
                builder.task_kinds
                  .map((kind) => TASK_KIND_LABELS[kind as TaskKind] ?? kind)
                  .join(", ") || "—"
              }
            />
          </dl>


          {isOperator ? (
            <button
              type="button"
              onClick={onOpenTechnical}
              className="text-[11px] text-emerald-300/90 hover:underline"
            >
              Show technical details
            </button>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => void handleToggleEnabled()}
            disabled={pending}
          >
            {builder.enabled ? "Turn off" : "Turn on"}
          </Button>
          {!confirmingDisable ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => setConfirmingDisable(true)}
              disabled={pending}
            >
              Disable
            </Button>
          ) : (
            <div className="flex flex-col items-end gap-1">
              <span className="text-[11px] text-[var(--theme-muted)]">
                Disabling means HAM won&apos;t pick this builder anymore. You can re-enable it
                later.
              </span>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirmingDisable(false)}
                  disabled={pending}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void handleDisable()}
                  disabled={pending}
                >
                  Yes, disable
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[6rem,1fr] gap-2">
      <dt className="text-[var(--theme-muted)]">{k}</dt>
      <dd className="break-words text-[var(--theme-text)]">{v}</dd>
    </div>
  );
}
