import * as React from "react";
import { Button } from "@/components/ui/button";
import type { BuilderPublic } from "../../adapters/builderStudioAdapter";

export function BuilderTechnicalDetailsDrawer({
  builder,
  isOperator,
  onClose,
}: {
  builder: BuilderPublic;
  isOperator: boolean;
  onClose: () => void;
}) {
  if (!isOperator) {
    if (typeof console !== "undefined") {
      console.warn("BuilderTechnicalDetailsDrawer rendered for a non-operator caller; suppressed.");
    }
    return null;
  }

  const details = builder.technical_details;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--theme-bg)] shadow-2xl"
        style={{ color: "var(--theme-text)" }}
      >
        <div className="border-b border-white/10 px-5 py-4">
          <h2 className="text-base font-semibold">Technical details</h2>
          <p className="mt-0.5 text-xs text-[var(--theme-muted)]">
            Read-only operator view. Fields surface the compiled build profile.
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm">
          {details ? (
            <dl className="space-y-3">
              <div>
                <dt className="text-[10px] uppercase tracking-wider text-[var(--theme-muted)]">
                  Harness
                </dt>
                <dd className="mt-1 font-mono text-xs text-[var(--theme-text)]">
                  {details.harness}
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wider text-[var(--theme-muted)]">
                  Compiled permission summary
                </dt>
                <dd>
                  <pre className="mt-1 whitespace-pre-wrap break-words rounded-md border border-[var(--theme-border)] bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-[var(--theme-text)]">
                    {details.compiled_permission_summary}
                  </pre>
                </dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wider text-[var(--theme-muted)]">
                  Model reference
                </dt>
                <dd className="mt-1 font-mono text-xs text-[var(--theme-text)]">
                  {details.model_ref ?? "—"}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-[var(--theme-muted)]">
              Technical details are unavailable for this builder.
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-white/10 px-5 py-3">
          <Button type="button" size="sm" variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
