/**
 * Reusable multi-select for Hermes **runtime** skills catalog (not Cursor operator skills).
 */
import * as React from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import type { HermesSkillCatalogEntry } from "@/lib/ham/api";

function TrustBadge({ level }: { level: string }) {
  const muted =
    level === "community"
      ? "border-amber-500/40 text-amber-500/70 bg-amber-500/5"
      : level === "trusted"
        ? "border-blue-500/40 text-blue-400/80 bg-blue-500/5"
        : level === "official" || level === "builtin"
          ? "border-emerald-500/40 text-emerald-400/80 bg-emerald-500/5"
          : "border-white/15 text-white/50 bg-white/[0.03]";
  return (
    <span
      className={cn(
        "text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border shrink-0",
        muted,
      )}
    >
      {level}
    </span>
  );
}

export interface HermesSkillPickerProps {
  entries: HermesSkillCatalogEntry[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  className?: string;
}

export function HermesSkillPicker({
  entries,
  selectedIds,
  onChange,
  disabled = false,
  className,
}: HermesSkillPickerProps) {
  const [q, setQ] = React.useState("");
  const selected = React.useMemo(() => new Set(selectedIds), [selectedIds]);

  const filtered = React.useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return entries;
    return entries.filter((e) => {
      const hay = `${e.catalog_id} ${e.display_name} ${e.summary}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [entries, q]);

  const toggle = (id: string) => {
    if (disabled) return;
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange([...next].sort());
  };

  const remove = (id: string) => {
    if (disabled) return;
    onChange(selectedIds.filter((x) => x !== id));
  };

  return (
    <div className={cn("space-y-3", className)}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/25" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search Hermes runtime catalog…"
          disabled={disabled}
          className="pl-9 h-9 bg-black/50 border-white/10 text-[11px] font-bold text-white placeholder:text-white/25"
        />
      </div>
      {selectedIds.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedIds.map((id) => (
            <button
              key={id}
              type="button"
              disabled={disabled}
              onClick={() => remove(id)}
              className={cn(
                "group flex items-center gap-1.5 pl-2 pr-1 py-1 rounded border border-[#FF6B00]/30 bg-[#FF6B00]/10 text-[9px] font-mono text-[#FF6B00]/90 max-w-full",
                disabled && "opacity-40 cursor-not-allowed",
              )}
            >
              <span className="truncate">{id}</span>
              <X className="h-3 w-3 shrink-0 opacity-60 group-hover:opacity-100" />
            </button>
          ))}
        </div>
      )}
      <div className="max-h-56 overflow-y-auto rounded-lg border border-white/10 bg-black/40 divide-y divide-white/5">
        {filtered.slice(0, 200).map((e) => {
          const on = selected.has(e.catalog_id);
          return (
            <label
              key={e.catalog_id}
              className={cn(
                "flex items-start gap-3 p-3 cursor-pointer hover:bg-white/[0.03]",
                disabled && "pointer-events-none opacity-40",
              )}
            >
              <input
                type="checkbox"
                checked={on}
                disabled={disabled}
                onChange={() => toggle(e.catalog_id)}
                className="mt-1 rounded border-white/20 bg-black"
              />
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-black text-white uppercase tracking-tight truncate">
                    {e.display_name}
                  </span>
                  <TrustBadge level={e.trust_level} />
                  {e.has_scripts ? (
                    <span className="text-[8px] font-black uppercase text-white/35">scripts</span>
                  ) : null}
                </div>
                <p className="text-[9px] font-bold text-white/35 leading-snug line-clamp-2">
                  {e.summary}
                </p>
                <p className="text-[8px] font-mono text-white/20 truncate">{e.catalog_id}</p>
              </div>
            </label>
          );
        })}
        {filtered.length === 0 && (
          <p className="p-4 text-[10px] font-bold text-white/30 uppercase tracking-widest">
            No matches
          </p>
        )}
        {filtered.length > 200 && (
          <p className="p-2 text-[9px] font-bold text-white/25 text-center">
            Showing first 200 — refine search
          </p>
        )}
      </div>
    </div>
  );
}
