import * as React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, Cpu } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";
import { cn } from "@/lib/utils";

function bandOf(m: ModelCatalogItem): "recommended" | "experimental" {
  return m.composer_model_band === "recommended" ? "recommended" : "experimental";
}

function selectedLabel(
  catalog: ModelCatalogPayload,
  candidates: ModelCatalogItem[],
  modelId: string | null,
  byokPickerActive: boolean,
): string {
  if (modelId) {
    const row = candidates.find((m) => m.id === modelId);
    const base = row ? row.label || row.id : modelId;
    if (byokPickerActive) return `OpenRouter BYOK · ${base}`;
    return base;
  }
  if ((catalog.gateway_mode || "").toLowerCase() === "http") {
    return "Hermes Agent / Default";
  }
  const first = candidates.find((c) => c.supports_chat);
  return first ? first.label || first.id : "Model";
}

type WorkspaceOpenRouterModelPickerProps = {
  catalog: ModelCatalogPayload;
  candidates: ModelCatalogItem[];
  modelId: string | null;
  onModelIdChange: (id: string | null) => void;
  disabled?: boolean;
  title?: string | null;
  triggerRef?: React.RefObject<HTMLButtonElement | null>;
  /** True when http gateway + user BYOK + a non-default OpenRouter id is selected (BYOK actor route). */
  byokPickerActive?: boolean;
  /** Model ids that recently failed with `OPENROUTER_MODEL_REJECTED` (session UX only). */
  failedModelIds?: ReadonlySet<string> | null;
  /** Narrow command-column layouts: shrink trigger + tighten truncation. */
  layoutDensity?: "comfortable" | "compact" | "tight";
};

export function WorkspaceOpenRouterModelPicker({
  catalog,
  candidates,
  modelId,
  onModelIdChange,
  disabled = false,
  title = null,
  triggerRef,
  byokPickerActive = false,
  failedModelIds = null,
  layoutDensity = "comfortable",
}: WorkspaceOpenRouterModelPickerProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  const q = query.trim().toLowerCase();

  const filtered = React.useMemo(() => {
    if (!q) return candidates;
    return candidates.filter((m) => {
      const blob = `${m.label}\n${m.id}\n${m.description ?? ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [candidates, q]);

  const recommendedRows = React.useMemo(
    () => candidates.filter((m) => bandOf(m) === "recommended"),
    [candidates],
  );
  const experimentalRows = React.useMemo(
    () => candidates.filter((m) => bandOf(m) === "experimental"),
    [candidates],
  );

  const gatewayMode = (catalog.gateway_mode || "").toLowerCase();
  const label = selectedLabel(catalog, candidates, modelId, byokPickerActive);

  const renderRow = (m: ModelCatalogItem) => {
    const failed = failedModelIds?.has(m.id) ?? false;
    const canSelect = m.supports_chat;
    const hint = [
      m.disabled_reason,
      failed ? "OpenRouter rejected this model on a recent turn." : null,
    ]
      .filter(Boolean)
      .join(" — ");
    return (
      <DropdownMenu.Item
        key={m.id}
        disabled={!canSelect}
        title={hint || undefined}
        className={cn(
          "flex cursor-pointer select-none rounded-md px-2 py-1.5 text-[12px] text-[#e6eef6] outline-none",
          "focus:bg-white/[0.06] data-[highlighted]:bg-white/[0.06]",
          !canSelect && "cursor-not-allowed opacity-55",
        )}
        onSelect={() => {
          if (canSelect) onModelIdChange(m.id);
        }}
      >
        <span className="min-w-0 flex-1 truncate">
          <span className="font-medium">
            {m.label || m.id}
            {failed ? (
              <span className="ml-1 text-[10px] font-normal text-amber-200/80">(rejected)</span>
            ) : null}
          </span>
          {m.id !== (m.label || "") ? (
            <span className="mt-0.5 block truncate font-mono text-[10px] text-white/35">
              {m.id}
            </span>
          ) : null}
          {!canSelect && m.disabled_reason ? (
            <span className="mt-0.5 block text-[10px] text-white/40">{m.disabled_reason}</span>
          ) : null}
        </span>
        {modelId === m.id ? (
          <span className="shrink-0 pl-2 text-[10px] text-emerald-300/90">✓</span>
        ) : null}
      </DropdownMenu.Item>
    );
  };

  return (
    <DropdownMenu.Root
      modal={false}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <DropdownMenu.Trigger asChild>
        <Button
          ref={triggerRef}
          type="button"
          id="hww-chat-model"
          variant="ghost"
          disabled={disabled}
          title={title ?? undefined}
          aria-label={layoutDensity === "tight" ? `Model: ${label}` : "Model"}
          className={cn(
            "hww-input ml-0 flex shrink-0 items-center justify-between gap-1 rounded-md border border-transparent",
            "bg-transparent text-left font-normal text-emerald-100/92 shadow-none hover:bg-white/[0.06] hover:text-emerald-50",
            "focus-visible:ring-2 focus-visible:ring-emerald-400/35 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent",
            layoutDensity === "comfortable" &&
              "h-8 min-h-8 max-w-[min(14rem,calc(100vw-10rem))] px-2 py-0 text-[10px] md:max-w-[min(18rem,calc(100vw-12rem))] md:text-[11px]",
            layoutDensity === "compact" &&
              "h-8 min-h-[32px] max-w-[min(11rem,45vw)] px-2 py-0 text-[10px] md:max-w-[min(14rem,50vw)]",
            layoutDensity === "tight" &&
              "h-8 min-h-8 w-8 min-w-8 max-w-8 flex-none justify-center px-0 py-0 text-[10px]",
          )}
        >
          {layoutDensity === "tight" ? (
            <Cpu className="h-4 w-4 shrink-0 opacity-90" aria-hidden />
          ) : (
            <span className="min-w-0 flex-1 truncate">{label}</span>
          )}
          <span className="flex shrink-0 items-center gap-0.5">
            {byokPickerActive && layoutDensity !== "tight" ? (
              <span className="shrink-0 rounded border border-emerald-400/35 px-1 text-[9px] font-semibold uppercase tracking-wide text-emerald-200/90">
                BYOK
              </span>
            ) : null}
            {layoutDensity === "tight" ? null : (
              <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
            )}
          </span>
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className={cn(
            "z-[200] w-[min(22rem,calc(100vw-1.5rem))] overflow-hidden rounded-xl border border-white/[0.12]",
            "bg-[#071010]/95 p-0 shadow-[0_12px_40px_rgba(0,0,0,0.55)] backdrop-blur-md md:w-[26rem]",
          )}
          onCloseAutoFocus={(e) => e.preventDefault()}
        >
          <div className="border-b border-white/[0.08] px-2 py-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models…"
              className="h-8 border-white/[0.1] bg-white/[0.04] text-[12px] text-[#e8eef3] placeholder:text-white/35"
              onKeyDown={(e) => e.stopPropagation()}
            />
          </div>
          <div className="max-h-[min(340px,50vh)] overflow-y-auto px-1 py-1">
            {gatewayMode === "http" ? (
              <>
                <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
                  Hermes default
                </div>
                <div className="px-2 pb-1 text-[11px] leading-snug text-white/45">
                  Gateway-controlled model. Choose an OpenRouter row below only when Connected Tools
                  OpenRouter (BYOK) is active.
                </div>
                <DropdownMenu.Item
                  className={cn(
                    "flex cursor-pointer select-none rounded-md px-2 py-1.5 text-[12px] text-emerald-100/95 outline-none",
                    "focus:bg-emerald-500/15 data-[highlighted]:bg-emerald-500/15",
                  )}
                  onSelect={() => onModelIdChange(null)}
                >
                  <span className="min-w-0 flex-1 truncate">Hermes Agent / Default</span>
                  {modelId === null ? (
                    <span className="shrink-0 pl-2 text-[10px] text-emerald-300/90">✓</span>
                  ) : null}
                </DropdownMenu.Item>
                {recommendedRows.length > 0 || experimentalRows.length > 0 || q ? (
                  <DropdownMenu.Separator className="my-1 h-px bg-white/[0.08]" />
                ) : null}
              </>
            ) : null}

            {q ? (
              <>
                {filtered.map((m) => renderRow(m))}
                {filtered.length === 0 ? (
                  <div className="px-2 py-6 text-center text-[12px] text-white/45">
                    No matching models.
                  </div>
                ) : null}
              </>
            ) : (
              <>
                {recommendedRows.length > 0 ? (
                  <>
                    <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
                      Recommended
                    </div>
                    {recommendedRows.map((m) => renderRow(m))}
                    {experimentalRows.length > 0 ? (
                      <DropdownMenu.Separator className="my-1 h-px bg-white/[0.08]" />
                    ) : null}
                  </>
                ) : null}
                {experimentalRows.length > 0 ? (
                  <>
                    <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
                      Experimental
                      {typeof catalog.openrouter_catalog?.remote_model_count === "number"
                        ? ` (${catalog.openrouter_catalog.remote_model_count} from OpenRouter)`
                        : null}
                    </div>
                    {experimentalRows.map((m) => renderRow(m))}
                  </>
                ) : null}
                {recommendedRows.length === 0 && experimentalRows.length === 0 ? (
                  <div className="px-2 py-6 text-center text-[12px] text-white/45">No models.</div>
                ) : null}
              </>
            )}
          </div>
          <div className="border-t border-white/[0.08] px-2 py-2">
            <DropdownMenu.Item asChild>
              <Link
                to="/workspace/settings?section=hermes#openrouter-models"
                className="block cursor-pointer rounded-md px-2 py-1.5 text-[12px] text-emerald-200/90 underline-offset-2 hover:bg-emerald-500/10 hover:underline focus:outline-none"
              >
                View all models in settings
              </Link>
            </DropdownMenu.Item>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
