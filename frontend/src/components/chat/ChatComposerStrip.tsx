import * as React from "react";
import {
  Box,
  Brain,
  ChevronDown,
  Factory,
  HelpCircle,
  Infinity,
  ListTree,
  Radio,
  Search,
  Sparkles,
  User,
  Wrench,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";

export type WorkbenchMode = "ask" | "plan" | "agent";

/** Execution system / backend family — not Ask/Plan/Agent (directive intent). */
export type UplinkId = "cloud_agent" | "factory_ai" | "eliza_os";

const MODES: { id: WorkbenchMode; label: string; hint: string; icon: React.ElementType }[] = [
  {
    id: "ask",
    label: "Ask",
    hint: "Direct help: explain, inspect, review, answer — lowest autonomy",
    icon: HelpCircle,
  },
  {
    id: "plan",
    label: "Plan",
    hint: "Structure the path: scope, risks, files, acceptance — before execution",
    icon: ListTree,
  },
  {
    id: "agent",
    label: "Agent",
    hint: "Delegated execution: carry the mission until blocked or done",
    icon: Infinity,
  },
];

const WORKERS: { id: string; label: string; hint: string }[] = [
  { id: "builder", label: "Builder", hint: "Core developer & logic implementation" },
  { id: "reviewer", label: "Reviewer", hint: "Code quality & security auditor" },
  { id: "researcher", label: "Researcher", hint: "Documentation & technical search" },
  { id: "coordinator", label: "Coordinator", hint: "Task decomposition & planning" },
  { id: "qa", label: "QA", hint: "Test generation & validation" },
];

const UPLINKS: {
  id: UplinkId;
  label: string;
  short: string;
  hint: string;
  icon: React.ElementType;
}[] = [
  {
    id: "cloud_agent",
    label: "Cloud Agent",
    short: "CLOUD",
    hint: "Cursor Cloud Agents API (launch, status, conversation, follow-up)",
    icon: Radio,
  },
  {
    id: "factory_ai",
    label: "Factory AI",
    short: "FACTORY",
    hint: "Hermes / OpenRouter path — factory-style execution profile",
    icon: Factory,
  },
  {
    id: "eliza_os",
    label: "ELIZA_OS",
    short: "ELIZA_OS",
    hint: "ELIZA_OS profile — dashboard chat until dedicated backend ships",
    icon: Sparkles,
  },
];

function uplinkAccentClass(id: UplinkId): string {
  if (id === "cloud_agent") return "text-[#00E5FF] border-[#00E5FF]/35";
  if (id === "factory_ai") return "text-[#BC13FE] border-[#BC13FE]/35";
  return "text-[#FF2BD6] border-[#FF2BD6]/35";
}

export interface ChatComposerStripProps {
  workbenchMode: WorkbenchMode;
  onWorkbenchMode: (m: WorkbenchMode) => void;
  modelId: string | null;
  onModelId: (id: string | null) => void;
  maxMode: boolean;
  onMaxMode: (v: boolean) => void;
  worker: string;
  onWorker: (id: string) => void;
  uplinkId: UplinkId;
  onUplinkId: (id: UplinkId) => void;
  toolsCount: number;
  catalog: ModelCatalogPayload | null;
  catalogLoading: boolean;
}

function findItem(items: ModelCatalogItem[], id: string | null): ModelCatalogItem | undefined {
  if (!id) return undefined;
  return items.find((x) => x.id === id);
}

export function ChatComposerStrip({
  workbenchMode,
  onWorkbenchMode,
  modelId,
  onModelId,
  maxMode,
  onMaxMode,
  worker,
  onWorker,
  uplinkId,
  onUplinkId,
  toolsCount,
  catalog,
  catalogLoading,
}: ChatComposerStripProps) {
  const [modeOpen, setModeOpen] = React.useState(false);
  const [modelOpen, setModelOpen] = React.useState(false);
  const [workerOpen, setWorkerOpen] = React.useState(false);
  const [uplinkOpen, setUplinkOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");

  const modeRef = React.useRef<HTMLDivElement>(null);
  const modelRef = React.useRef<HTMLDivElement>(null);
  const workerRef = React.useRef<HTMLDivElement>(null);
  const uplinkRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const close = (e: MouseEvent) => {
      const t = e.target as Node;
      if (modeRef.current?.contains(t)) return;
      if (modelRef.current?.contains(t)) return;
      if (workerRef.current?.contains(t)) return;
      if (uplinkRef.current?.contains(t)) return;
      setModeOpen(false);
      setModelOpen(false);
      setWorkerOpen(false);
      setUplinkOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const items = catalog?.items ?? [];
  const selected = findItem(items, modelId);
  const modeDef = MODES.find((m) => m.id === workbenchMode) ?? MODES[2];
  const ModeIcon = modeDef.icon;
  const workerDef = WORKERS.find((w) => w.id === worker) ?? WORKERS[0];
  const uplinkDef = UPLINKS.find((u) => u.id === uplinkId) ?? UPLINKS[1];
  const UplinkIcon = uplinkDef.icon;

  const tierAuto = items.find((i) => i.id === "tier:auto");
  const tierPremium = items.find((i) => i.id === "tier:premium");

  const q = search.trim().toLowerCase();
  const listItems = items.filter((it) => {
    if (it.id === "tier:auto" || it.id === "tier:premium") return false;
    if (!q) return true;
    return (
      it.label.toLowerCase().includes(q) ||
      it.id.toLowerCase().includes(q) ||
      (it.description || "").toLowerCase().includes(q)
    );
  });

  const selectModel = (it: ModelCatalogItem) => {
    if (!it.supports_chat) return;
    onModelId(it.id);
    setModelOpen(false);
    setSearch("");
  };

  return (
    <div className="flex flex-wrap items-center gap-2 px-4 pt-4 pb-3">
      {/* Ask / Plan / Agent — directive intent */}
      <div className="relative" ref={modeRef}>
        <button
          type="button"
          onClick={() => {
            setModeOpen(!modeOpen);
            setModelOpen(false);
            setWorkerOpen(false);
            setUplinkOpen(false);
          }}
          className={cn(
            "inline-flex items-center gap-2 h-10 px-3 rounded-lg border text-[10px] font-black uppercase tracking-widest transition-colors",
            modeOpen
              ? "bg-[#FF6B00] border-[#FF6B00] text-black ring-2 ring-[#FF6B00]/30"
              : "bg-[#FF6B00] border-[#FF6B00] text-black hover:brightness-110",
          )}
        >
          <ModeIcon className="h-3.5 w-3.5 shrink-0" />
          {modeDef.label}
          <ChevronDown className={cn("h-3 w-3 opacity-50", modeOpen && "rotate-180")} />
        </button>
        {modeOpen && (
          <div className="absolute left-0 bottom-full mb-1 z-50 w-72 rounded-lg border border-white/10 bg-[#0a0a0a] shadow-2xl py-1">
            {MODES.map((m) => {
              const I = m.icon;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => {
                    onWorkbenchMode(m.id);
                    setModeOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-white/5 transition-colors",
                    workbenchMode === m.id ? "bg-[#FF6B00]/10" : "",
                  )}
                >
                  <I className="h-4 w-4 mt-0.5 shrink-0 text-[#FF6B00]/80" />
                  <div>
                    <div className="text-[10px] font-black uppercase tracking-widest text-white">{m.label}</div>
                    <div className="text-[9px] font-bold text-white/35 uppercase tracking-wider mt-0.5 leading-snug">{m.hint}</div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Model */}
      <div className="relative flex-1 min-w-[140px] max-w-[280px]" ref={modelRef}>
        <button
          type="button"
          onClick={() => {
            setModeOpen(false);
            setWorkerOpen(false);
            setUplinkOpen(false);
            setModelOpen(!modelOpen);
          }}
          className={cn(
            "flex items-center justify-between w-full h-10 px-3 rounded-lg border border-white/10 bg-white/[0.04] text-left hover:border-[#FF6B00]/30 transition-colors",
            modelOpen && "border-[#FF6B00]/50",
          )}
        >
          <span className="flex items-center gap-2 min-w-0">
            <Box className="h-3.5 w-3.5 text-[#FF6B00] shrink-0" />
            {!selected ? (
              <span className="text-[10px] font-black uppercase tracking-widest text-white/35">MODEL</span>
            ) : (
              <>
                <span className="text-[10px] font-black uppercase tracking-widest text-white truncate">{selected.label}</span>
                {selected.tag ? (
                  <span className="shrink-0 text-[8px] font-black uppercase px-1.5 py-0.5 rounded bg-[#FF6B00]/20 text-[#FF6B00]">
                    {selected.tag}
                  </span>
                ) : null}
              </>
            )}
          </span>
          <ChevronDown className={cn("h-3.5 w-3.5 text-white/30 shrink-0", modelOpen && "rotate-180")} />
        </button>
        {modelOpen && (
          <div className="absolute left-0 bottom-full mb-1 z-[200] flex w-[min(100vw-2rem,22rem)] max-h-[min(85vh,520px)] flex-col rounded-lg border border-white/10 bg-[#0a0a0a] shadow-2xl overflow-hidden">
            <div className="shrink-0 space-y-2 border-b border-white/5 p-2">
              <div className="flex items-center gap-2 rounded-md border border-white/10 bg-black/50 px-2 py-1.5">
                <Search className="h-3.5 w-3.5 shrink-0 text-white/25" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="SEARCH MODELS…"
                  className="flex-1 bg-transparent text-[10px] font-bold uppercase tracking-wider text-white placeholder:text-white/20 outline-none"
                />
              </div>
              <div className="flex items-center justify-between px-2">
                <span className="text-[9px] font-black text-white/30 uppercase tracking-widest">MAX MODE</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={maxMode}
                  onClick={() => onMaxMode(!maxMode)}
                  className={cn(
                    "relative h-5 w-9 rounded-full transition-colors",
                    maxMode ? "bg-emerald-500/80" : "bg-white/10",
                  )}
                >
                  <span
                    className={cn(
                      "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                      maxMode && "translate-x-4",
                    )}
                  />
                </button>
              </div>
            </div>
            {(tierAuto || tierPremium) && (
              <div className="shrink-0 space-y-1 border-b border-white/5 px-2 py-2">
                <div className="text-[8px] font-black text-white/20 uppercase tracking-[0.3em] px-1">Quick</div>
                <div className="grid grid-cols-2 gap-1">
                  {tierAuto && (
                    <button
                      type="button"
                      disabled={!tierAuto.supports_chat}
                      onClick={() => selectModel(tierAuto)}
                      className={cn(
                        "text-left px-2 py-2 rounded-md border text-[9px] font-black uppercase tracking-wider transition-colors",
                        tierAuto.supports_chat
                          ? "border-white/10 hover:bg-white/5 text-white/80"
                          : "border-white/5 opacity-40 cursor-not-allowed",
                      )}
                    >
                      <span className="flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#FF6B00]" />
                        Auto
                      </span>
                      <span className="block text-[8px] font-bold text-white/25 normal-case mt-1">Efficiency</span>
                    </button>
                  )}
                  {tierPremium && (
                    <button
                      type="button"
                      disabled={!tierPremium.supports_chat}
                      onClick={() => selectModel(tierPremium)}
                      className={cn(
                        "text-left px-2 py-2 rounded-md border text-[9px] font-black uppercase tracking-wider transition-colors",
                        tierPremium.supports_chat
                          ? "border-white/10 hover:bg-white/5 text-white/80"
                          : "border-white/5 opacity-40 cursor-not-allowed",
                      )}
                    >
                      Premium
                      <span className="block text-[8px] font-bold text-white/25 normal-case mt-1">Intelligence</span>
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="min-h-[200px] max-h-[min(42vh,320px)] overflow-y-auto overscroll-contain py-1 scrollbar-thin">
              {catalogLoading && (
                <div className="px-3 py-4 text-[9px] font-bold uppercase tracking-widest text-white/25">Loading catalog…</div>
              )}
              {!catalogLoading && listItems.length === 0 && (
                <div className="px-3 py-8 text-center text-[9px] font-bold uppercase tracking-widest text-white/30">
                  No models match your search.
                </div>
              )}
              {!catalogLoading &&
                listItems.map((it) => (
                  <button
                    key={it.id}
                    type="button"
                    disabled={!it.supports_chat}
                    onClick={() => selectModel(it)}
                    className={cn(
                      "flex w-full flex-col items-start gap-0.5 border-b border-white/[0.03] px-3 py-2.5 text-left transition-colors last:border-0",
                      it.supports_chat ? "hover:bg-white/[0.04]" : "cursor-not-allowed opacity-45",
                      modelId === it.id && "bg-[#FF6B00]/10",
                    )}
                  >
                    <div className="flex w-full items-center gap-2">
                      <Brain className="h-3.5 w-3.5 shrink-0 text-white/25" aria-hidden />
                      <span className="text-[10px] font-black uppercase tracking-tight text-white/90">{it.label}</span>
                      {it.tag ? (
                        <span className="rounded bg-white/10 px-1 py-0.5 text-[8px] font-black uppercase text-white/45">{it.tag}</span>
                      ) : null}
                      {it.provider === "cursor" ? (
                        <span className="ml-auto text-[8px] font-bold uppercase text-amber-500/70">Cursor</span>
                      ) : null}
                      {modelId === it.id && it.supports_chat ? (
                        <span className="text-[#FF6B00]">✓</span>
                      ) : null}
                    </div>
                    <span className="pl-6 text-[9px] font-bold leading-snug text-white/30">{it.description}</span>
                    {!it.supports_chat && it.disabled_reason ? (
                      <span className="mt-1 pl-6 text-[8px] font-bold leading-tight text-amber-500/60">{it.disabled_reason}</span>
                    ) : null}
                  </button>
                ))}
            </div>
            <button
              type="button"
              className="shrink-0 border-t border-white/5 px-3 py-2 text-[9px] font-black uppercase tracking-widest text-[#FF6B00]/80 transition-colors hover:text-[#FF6B00]"
              onClick={() => {
                setModelOpen(false);
              }}
            >
              + Add models
            </button>
          </div>
        )}
      </div>

      {/* Worker */}
      <div className="relative min-w-[120px]" ref={workerRef}>
        <button
          type="button"
          onClick={() => {
            setWorkerOpen(!workerOpen);
            setModeOpen(false);
            setModelOpen(false);
            setUplinkOpen(false);
          }}
          className={cn(
            "flex items-center justify-between w-full h-10 px-3 rounded-lg border border-white/10 bg-white/[0.04] text-left hover:border-white/20 transition-colors",
            workerOpen && "border-[#FF6B00]/30",
          )}
        >
          <span className="flex items-center gap-2 min-w-0">
            <User className="h-3.5 w-3.5 text-white/35 shrink-0" />
            <span className="text-[10px] font-black uppercase tracking-widest text-white/80 truncate">{workerDef.label}</span>
          </span>
          <ChevronDown className={cn("h-3.5 w-3.5 text-white/30 shrink-0", workerOpen && "rotate-180")} />
        </button>
        {workerOpen && (
          <div className="absolute left-0 bottom-full mb-1 z-50 w-72 rounded-lg border border-white/10 bg-[#0a0a0a] shadow-2xl py-1 max-h-64 overflow-y-auto">
            <div className="px-3 py-1.5 text-[8px] font-black text-white/25 uppercase tracking-[0.25em]">Active worker workforce</div>
            {WORKERS.map((w) => (
              <button
                key={w.id}
                type="button"
                onClick={() => {
                  onWorker(w.id);
                  setWorkerOpen(false);
                }}
                className={cn(
                  "flex w-full items-start gap-3 px-3 py-2 text-left hover:bg-white/5",
                  worker === w.id ? "bg-white/[0.04]" : "",
                )}
              >
                <User className="h-3.5 w-3.5 text-white/25 shrink-0 mt-0.5" />
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-white">{w.label}</div>
                  <div className="text-[9px] font-bold text-white/25 uppercase tracking-wider mt-0.5 line-clamp-2">{w.hint}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Uplink — execution system / backend family */}
      <div className="relative min-w-[130px]" ref={uplinkRef}>
        <button
          type="button"
          onClick={() => {
            setUplinkOpen(!uplinkOpen);
            setModeOpen(false);
            setModelOpen(false);
            setWorkerOpen(false);
          }}
          className={cn(
            "flex items-center justify-between w-full h-10 px-3 rounded-lg border bg-white/[0.04] text-left transition-colors",
            uplinkOpen ? "border-[#FF6B00]/50" : "border-white/10 hover:border-white/20",
            uplinkAccentClass(uplinkId),
          )}
        >
          <span className="flex items-center gap-2 min-w-0">
            <UplinkIcon className="h-3.5 w-3.5 shrink-0 opacity-90" />
            <span className="text-[10px] font-black uppercase tracking-widest truncate">{uplinkDef.short}</span>
          </span>
          <ChevronDown className={cn("h-3.5 w-3.5 text-white/30 shrink-0", uplinkOpen && "rotate-180")} />
        </button>
        {uplinkOpen && (
          <div className="absolute left-0 bottom-full mb-1 z-[200] w-80 rounded-lg border border-white/10 bg-[#0a0a0a] shadow-2xl py-1">
            <div className="px-3 py-1.5 text-[8px] font-black text-white/25 uppercase tracking-[0.25em]">Uplink</div>
            {UPLINKS.map((u) => {
              const I = u.icon;
              return (
                <button
                  key={u.id}
                  type="button"
                  onClick={() => {
                    onUplinkId(u.id);
                    setUplinkOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-white/5 transition-colors",
                    uplinkId === u.id ? "bg-white/[0.06]" : "",
                  )}
                >
                  <I className={cn("h-4 w-4 mt-0.5 shrink-0", uplinkAccentClass(u.id))} />
                  <div>
                    <div className={cn("text-[10px] font-black uppercase tracking-widest", uplinkAccentClass(u.id))}>{u.label}</div>
                    <div className="text-[9px] font-bold text-white/35 uppercase tracking-wider mt-0.5 leading-snug">{u.hint}</div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Tools */}
      <div className="inline-flex items-center gap-2 h-10 px-3 rounded-lg border border-white/10 bg-white/[0.02] text-white/35 shrink-0">
        <Wrench className="h-3.5 w-3.5" />
        <span className="text-[9px] font-black uppercase tracking-widest">{toolsCount} tools enabled</span>
      </div>
    </div>
  );
}
