import * as React from "react";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";
import { cn } from "@/lib/utils";

const QUICK_TIER_IDS = new Set(["openrouter:default", "tier:auto", "tier:premium"]);

function quickPickIds(candidates: ModelCatalogItem[]): string[] {
  const tiers = candidates.filter((m) => QUICK_TIER_IDS.has(m.id));
  const rest = candidates.filter((m) => !QUICK_TIER_IDS.has(m.id));
  const ordered = [...tiers, ...rest];
  return ordered.slice(0, 5).map((m) => m.id);
}

function selectedLabel(candidates: ModelCatalogItem[], modelId: string | null): string {
  if (modelId) {
    const row = candidates.find((m) => m.id === modelId);
    if (row) return row.label || row.id;
    return modelId;
  }
  const first = candidates[0];
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
};

export function WorkspaceOpenRouterModelPicker({
  catalog,
  candidates,
  modelId,
  onModelIdChange,
  disabled = false,
  title = null,
  triggerRef,
}: WorkspaceOpenRouterModelPickerProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  const quickIds = React.useMemo(() => new Set(quickPickIds(candidates)), [candidates]);

  const q = query.trim().toLowerCase();

  const filtered = React.useMemo(() => {
    if (!q) return candidates;
    return candidates.filter((m) => {
      const blob = `${m.label}\n${m.id}\n${m.description ?? ""}`.toLowerCase();
      return blob.includes(q);
    });
  }, [candidates, q]);

  const quickShown = React.useMemo(() => {
    if (q) return [];
    return candidates.filter((m) => quickIds.has(m.id));
  }, [candidates, quickIds, q]);

  const restShown = React.useMemo(() => {
    if (q) return filtered;
    return candidates.filter((m) => !quickIds.has(m.id));
  }, [candidates, filtered, quickIds, q]);

  const label = selectedLabel(candidates, modelId);

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
          aria-label="Model"
          className={cn(
            "hww-input ml-0.5 max-w-[min(22rem,85vw)] shrink justify-between gap-1 rounded-md border-0",
            "bg-emerald-500/10 px-2 py-1 text-left text-[11px] font-normal text-emerald-200/90 hover:bg-emerald-500/16",
            "md:max-w-[min(26rem,90vw)] md:py-1.5 md:pl-2.5 md:pr-2 md:text-[12px]",
          )}
        >
          <span className="min-w-0 truncate">{label}</span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
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
            {!q && quickShown.length > 0 ? (
              <>
                <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
                  Quick picks
                </div>
                {quickShown.map((m) => (
                  <DropdownMenu.Item
                    key={`q-${m.id}`}
                    className={cn(
                      "flex cursor-pointer select-none rounded-md px-2 py-1.5 text-[12px] text-emerald-100/95 outline-none",
                      "focus:bg-emerald-500/15 data-[highlighted]:bg-emerald-500/15",
                    )}
                    onSelect={() => onModelIdChange(m.id)}
                  >
                    <span className="min-w-0 flex-1 truncate">{m.label || m.id}</span>
                    {modelId === m.id ? (
                      <span className="shrink-0 pl-2 text-[10px] text-emerald-300/90">✓</span>
                    ) : null}
                  </DropdownMenu.Item>
                ))}
                {restShown.length > 0 ? <DropdownMenu.Separator className="my-1 h-px bg-white/[0.08]" /> : null}
              </>
            ) : null}
            {!q && restShown.length > 0 ? (
              <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wide text-white/40">
                All models
                {typeof catalog.openrouter_catalog?.remote_model_count === "number"
                  ? ` (${catalog.openrouter_catalog.remote_model_count} from OpenRouter)`
                  : null}
              </div>
            ) : null}
            {(q ? filtered : restShown).map((m) => (
              <DropdownMenu.Item
                key={m.id}
                className={cn(
                  "flex cursor-pointer select-none rounded-md px-2 py-1.5 text-[12px] text-[#e6eef6] outline-none",
                  "focus:bg-white/[0.06] data-[highlighted]:bg-white/[0.06]",
                )}
                onSelect={() => onModelIdChange(m.id)}
              >
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{m.label || m.id}</span>
                  {m.id !== (m.label || "") ? (
                    <span className="mt-0.5 block truncate font-mono text-[10px] text-white/35">{m.id}</span>
                  ) : null}
                </span>
                {modelId === m.id ? (
                  <span className="shrink-0 pl-2 text-[10px] text-emerald-300/90">✓</span>
                ) : null}
              </DropdownMenu.Item>
            ))}
            {(q ? filtered : restShown).length === 0 ? (
              <div className="px-2 py-6 text-center text-[12px] text-white/45">No matching models.</div>
            ) : null}
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
