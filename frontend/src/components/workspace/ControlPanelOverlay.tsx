import * as React from "react";
import {
  X,
  Activity,
  MessageSquare,
  Zap,
  Shield,
  Cpu,
  Terminal,
  History,
  Info,
  Layers,
  Box,
  GitBranch,
  Circle,
  AlertCircle,
  Search,
  Users,
  Database,
  Key,
  ToyBrick,
  Brain,
  Monitor,
  Layout,
  Settings as SettingsIcon,
  Archive,
  Cloud,
  ChevronRight,
  Plus,
  RefreshCw,
  MoreHorizontal,
  Command,
  Lock,
  Globe,
  Trash2,
  Edit2,
  Copy,
  Check,
  ExternalLink,
  Code,
  FileText,
  Save,
  Filter,
  Play,
  Eye,
  EyeOff,
  ShieldCheck,
  CloudDownload,
  Share2,
  Smartphone,
  Bell,
  HardDrive,
  BarChart3,
  FileSearch,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Agent } from "@/lib/ham/types";
import { useWorkspace } from "@/lib/ham/WorkspaceContext";
import { useAgent } from "@/lib/ham/AgentContext";

import { DroidConfigPanel } from "./DroidConfigPanel";

interface ControlPanelOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  activeTask: string;
  onTaskChange: (val: string) => void;
  selectedAgent: Agent;
}

type SectionId = "general" | "droids" | "activity";

export function ControlPanelOverlay({
  isOpen,
  onClose,
  activeTask,
  onTaskChange,
  selectedAgent,
}: ControlPanelOverlayProps) {
  const navigate = useNavigate();
  const { workspaceName, branch } = useWorkspace();
  const { agents, selectedAgentId, setSelectedAgentId } = useAgent();
  const [activeSegment, setActiveSegment] =
    React.useState<SectionId>("general");
  const [searchQuery, setSearchQuery] = React.useState("");

  if (!isOpen) return null;

  const sections = [
    {
      group: "WORK",
      items: [
        { id: "general", label: "Chat", icon: MessageSquare },
        { id: "activity", label: "Activity", icon: History },
        { id: "droids", label: "Droids", icon: Cpu },
      ],
    },
  ];

  const goToSettings = (tab?: string) => {
    onClose();
    if (tab) {
      navigate(`/settings?tab=${encodeURIComponent(tab)}`);
    } else {
      navigate("/settings");
    }
  };


  return (
    <>
      {/* Backdrop Dimming with Blur */}
      <div
        className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] animate-in fade-in duration-300"
        onClick={onClose}
      />

      {/* Large Settings-Style Panel */}
      <div className="fixed inset-4 md:inset-10 lg:inset-20 bg-[#080808] border border-white/5 z-[101] animate-in zoom-in-95 duration-300 shadow-[0_0_100px_rgba(0,0,0,0.8)] overflow-hidden rounded-xl flex flex-col md:flex-row">
        {/* LEFT COLUMN: NAVIGATION */}
        <div className="w-full md:w-72 bg-[#0c0c0c] border-r border-white/5 flex flex-col shrink-0">
          {/* Header Area */}
          <div className="p-6 space-y-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 bg-[#FF6B00] rounded-lg flex items-center justify-center shadow-[0_0_15px_rgba(255,107,0,0.3)]">
                  <Activity className="h-4 w-4 text-black" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[10px] font-black text-white uppercase tracking-widest leading-none">
                    HAM_WORKBENCH
                  </span>
                  <span className="text-[8px] font-bold text-white/20 uppercase tracking-[0.2em] mt-1 italic">
                    v2.5.0 STABLE
                  </span>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1 hover:bg-white/5 rounded-md text-white/20 hover:text-white md:hidden"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Search Field */}
            <div className="relative group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/20 group-focus-within:text-[#FF6B00] transition-colors" />
              <input
                type="text"
                placeholder="Search control panel"
                className="w-full bg-white/[0.02] border border-white/5 rounded-lg pl-9 pr-12 py-2 text-[11px] font-bold text-white/60 placeholder:text-white/10 outline-none focus:border-[#FF6B00]/40 focus:bg-white/[0.04] transition-all"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-40">
                <span className="text-[10px] border border-white/10 px-1 rounded bg-white/5">
                  ⌘
                </span>
                <span className="text-[9px] border border-white/10 px-1 rounded bg-white/5 font-mono">
                  P
                </span>
              </div>
            </div>
          </div>

          {/* Navigation Groups */}
          <div className="flex-1 overflow-y-auto px-4 py-2 space-y-8 scrollbar-hide pb-10">
            {sections.map((group) => (
              <div key={group.group} className="space-y-1">
                <h3 className="px-4 text-[9px] font-black text-white/10 uppercase tracking-[0.4em] mb-4">
                  {group.group}
                </h3>
                <div className="space-y-0.5">
                  {group.items
                    .filter((item) =>
                      item.label
                        .toLowerCase()
                        .includes(searchQuery.toLowerCase()),
                    )
                    .map((item) => (
                      <button
                        key={item.id}
                        onClick={() => setActiveSegment(item.id as SectionId)}
                        className={cn(
                          "w-full flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-left group",
                          activeSegment === item.id
                            ? "bg-[#FF6B00]/10 text-[#FF6B00]"
                            : "hover:bg-white/[0.03] text-white/30 hover:text-white",
                        )}
                      >
                        <item.icon
                          className={cn(
                            "h-4 w-4 transition-transform group-hover:scale-110",
                            activeSegment === item.id
                              ? "text-[#FF6B00]"
                              : "text-white/20 group-hover:text-white/40",
                          )}
                        />
                        <span className="text-[11px] font-bold uppercase tracking-wider">
                          {item.label}
                        </span>
                        {activeSegment === item.id && (
                          <div className="ml-auto h-1 w-1 rounded-full bg-[#FF6B00] shadow-[0_0_5px_#FF6B00]" />
                        )}
                      </button>
                    ))}
                </div>
                {group.group === "WORK" && (
                  <div className="mx-4 mt-6 h-px bg-white/[0.03]" />
                )}
              </div>
            ))}
          </div>

          {/* Full settings live on /settings (nav rail cog) — jump links only */}
          <div className="px-4 pb-4 space-y-2 border-t border-white/5 pt-4 shrink-0">
            <h3 className="px-4 text-[9px] font-black text-white/10 uppercase tracking-[0.35em] mb-2">
              Configuration
            </h3>
            <button
              type="button"
              onClick={() => goToSettings()}
              className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all text-left bg-[#FF6B00]/10 text-[#FF6B00] border border-[#FF6B00]/25 hover:bg-[#FF6B00]/15"
            >
              <SettingsIcon className="h-4 w-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider">
                Full settings
              </span>
            </button>
            <div className="flex flex-col gap-1 px-2">
              <button
                type="button"
                onClick={() => goToSettings("api-keys")}
                className="text-left px-2 py-1.5 text-[10px] font-bold uppercase tracking-widest text-white/35 hover:text-[#FF6B00] transition-colors"
              >
                API keys
              </button>
              <button
                type="button"
                onClick={() => goToSettings("environment")}
                className="text-left px-2 py-1.5 text-[10px] font-bold uppercase tracking-widest text-white/35 hover:text-[#FF6B00] transition-colors"
              >
                Environment
              </button>
              <button
                type="button"
                onClick={() => goToSettings("tools-extensions")}
                className="text-left px-2 py-1.5 text-[10px] font-bold uppercase tracking-widest text-white/35 hover:text-[#FF6B00] transition-colors"
              >
                Tools &amp; extensions
              </button>
            </div>
          </div>

          {/* User Profile Area */}
          <div className="p-6 border-t border-white/5 bg-black/20">
            <div className="flex items-center gap-4">
              <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-zinc-800 to-black border border-white/10 flex items-center justify-center overflow-hidden">
                <img
                  src="https://picsum.photos/seed/aaron/100/100"
                  className="w-full h-full object-cover opacity-80"
                  referrerPolicy="no-referrer"
                  alt=""
                />
              </div>
              <div className="flex flex-col overflow-hidden">
                <span className="text-[11px] font-black text-white uppercase tracking-tight truncate">
                  AARON_BUNDY_V2
                </span>
                <div className="flex items-center gap-2 mt-0.5">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00]" />
                  <span className="text-[8px] font-bold text-white/20 uppercase tracking-widest">
                    Supervisor Mode
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: CONTENT PANE */}
        <div className="flex-1 flex flex-col relative bg-[#050505]">
          {/* Section Header */}
          <div className="h-16 flex items-center px-10 border-b border-white/5 justify-between">
            <div className="flex items-center gap-4">
              <h2 className="text-xl font-black text-white uppercase italic tracking-tighter">
                {
                  sections
                    .flatMap((g) => g.items)
                    .find((i) => i.id === activeSegment)?.label
                }
              </h2>
              <div className="h-4 w-px bg-white/10" />
              <span className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] italic capitalize">
                {sections
                  .find((g) => g.items.some((i) => i.id === activeSegment))
                  ?.group.toLowerCase()}
              </span>
            </div>
            <button
              onClick={onClose}
              className="flex items-center gap-2 px-3 py-1.5 hover:bg-white/5 rounded-lg border border-transparent hover:border-white/5 transition-all group"
            >
              <span className="text-[9px] font-black text-white/20 uppercase tracking-widest group-hover:text-[#FF6B00]">
                Done
              </span>
              <X className="h-4 w-4 text-white/20 group-hover:text-white" />
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-y-auto scrollbar-hide p-10 space-y-12 pb-32">
            {/* 1. CHAT (GENERAL) */}
            {activeSegment === "general" && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500 text-left pb-32 max-w-4xl">
                {/* 1. SESSION */}
                <div className="space-y-3">
                  <div className="flex items-center gap-3 px-1">
                    <span className="text-[10px] font-black text-white/60 uppercase tracking-[0.3em] italic">
                      Session
                    </span>
                    <div className="h-px flex-1 bg-gradient-to-r from-white/10 to-transparent" />
                  </div>
                  <div className="space-y-1">
                    {[
                      {
                        label: "Active Worker",
                        sub: "Primary agent interface assigned to this session",
                        value: selectedAgent.name,
                        status: "Connected",
                      },
                      {
                        label: "Active Team",
                        sub: "Current collaborative squad mapping",
                        value: "Alpha Squad",
                      },
                      {
                        label: "Quality Review",
                        sub: "Automated verification and health check",
                        value: "Verified Healthy",
                        isSuccess: true,
                      },
                      {
                        label: "Supervisor",
                        sub: "Logic orchestration engine",
                        value: "Hermes (Built-in)",
                      },
                    ].map((row) => (
                      <div
                        key={row.label}
                        className="flex items-center justify-between py-2 px-3 hover:bg-white/[0.01] transition-colors rounded-lg group border-b border-white/[0.03] last:border-0"
                      >
                        <div className="space-y-0.5">
                          <p className="text-[10px] font-black text-white/90 uppercase tracking-widest leading-none">
                            {row.label}
                          </p>
                          <p className="text-[8px] font-bold text-white/40 uppercase tracking-wider leading-none">
                            {row.sub}
                          </p>
                        </div>
                        <div className="flex items-center gap-4">
                          {row.status && (
                            <div className="flex items-center gap-1.5 px-2 py-0.5 bg-green-500/5 border border-green-500/20 rounded-md">
                              <div className="h-1 w-1 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                              <span className="text-[8px] font-black text-green-500/80 uppercase">
                                {row.status}
                              </span>
                            </div>
                          )}
                          <span
                            className={cn(
                              "text-[10px] font-bold uppercase italic tracking-widest px-2 py-0.5 bg-white/[0.02] border border-white/5 rounded text-white/60",
                              row.isSuccess ? "text-green-500/60" : "",
                            )}
                          >
                            {row.value}
                          </span>
                        </div>
                      </div>
                    ))}

                    {/* FOCUS PRESET - Interactive */}
                    <div className="flex items-center justify-between py-2.5 px-3 hover:bg-white/[0.02] transition-colors rounded-lg group border-b border-white/[0.03] last:border-0">
                      <div className="space-y-0.5">
                        <p className="text-[10px] font-black text-white/90 uppercase tracking-widest leading-none">
                          Focus Preset
                        </p>
                        <p className="text-[8px] font-bold text-white/40 uppercase tracking-wider leading-none">
                          Operational priority weighting
                        </p>
                      </div>
                      <select className="bg-black border border-white/10 rounded px-2 py-1 text-[10px] font-bold uppercase italic tracking-widest text-[#FF6B00] outline-none hover:border-[#FF6B00]/40 transition-colors cursor-pointer">
                        <option>Industrial Default</option>
                        <option>High Precision</option>
                        <option>Rapid Prototype</option>
                        <option>Logic Heavy</option>
                      </select>
                    </div>
                  </div>
                </div>

                {/* 2. WORKSPACE */}
                <div className="space-y-3">
                  <div className="flex items-center gap-3 px-1">
                    <span className="text-[10px] font-black text-white/60 uppercase tracking-[0.3em] italic">
                      Workspace
                    </span>
                    <div className="h-px flex-1 bg-gradient-to-r from-white/10 to-transparent" />
                  </div>
                  <div className="space-y-1">
                    {[
                      {
                        label: "Workspace",
                        sub: "Active repository context",
                        value: workspaceName,
                      },
                      {
                        label: "Branch",
                        sub: "Target version control reference",
                        value: branch,
                        isMono: true,
                      },
                      {
                        label: "Working State",
                        sub: "Indicators of local modifications",
                        value: "DIRTY_STATE",
                        isWarning: true,
                      },
                      {
                        label: "Execution Target",
                        sub: "Active runtime environment",
                        value: "Local Container",
                      },
                      {
                        label: "Last Sync",
                        sub: "Most recent temporal snapshot",
                        value: "18:32:04 (UTC)",
                      },
                    ].map((row) => (
                      <div
                        key={row.label}
                        className="flex items-center justify-between py-2 px-3 hover:bg-white/[0.01] transition-colors rounded-lg border-b border-white/[0.03] last:border-0"
                      >
                        <div className="space-y-0.5">
                          <p className="text-[10px] font-black text-white/90 uppercase tracking-widest leading-none">
                            {row.label}
                          </p>
                          <p className="text-[8px] font-bold text-white/40 uppercase tracking-wider leading-none">
                            {row.sub}
                          </p>
                        </div>
                        <span
                          className={cn(
                            "text-[10px] font-bold uppercase italic tracking-widest px-2 py-0.5 bg-white/[0.02] border border-white/5 rounded text-white/60",
                            row.isWarning ? "text-[#FF6B00]/80" : "",
                            row.isMono ? "font-mono" : "",
                          )}
                        >
                          {row.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 3. WORKBENCH */}
                <div className="space-y-3">
                  <div className="flex items-center gap-3 px-1">
                    <span className="text-[10px] font-black text-white/60 uppercase tracking-[0.3em] italic">
                      Workbench
                    </span>
                    <div className="h-px flex-1 bg-gradient-to-r from-white/10 to-transparent" />
                  </div>
                  <div className="space-y-1">
                    {[
                      {
                        label: "Preview",
                        sub: "Live rendering engine status",
                        value: "On",
                      },
                      {
                        label: "Browser",
                        sub: "External web access bridge",
                        value: "Off",
                      },
                      {
                        label: "Split View",
                        sub: "Interface spanning mode",
                        value: "On",
                      },
                      {
                        label: "Context Budget",
                        sub: "Memory and token footprint",
                        value: "~48.2K / 200,000",
                        isAccent: true,
                      },
                    ].map((row) => (
                      <div
                        key={row.label}
                        className="flex items-center justify-between py-2 px-3 hover:bg-white/[0.01] transition-colors rounded-lg border-b border-white/[0.03] last:border-0"
                      >
                        <div className="space-y-0.5">
                          <p className="text-[10px] font-black text-white/90 uppercase tracking-widest leading-none">
                            {row.label}
                          </p>
                          <p className="text-[8px] font-bold text-white/40 uppercase tracking-wider leading-none">
                            {row.sub}
                          </p>
                        </div>
                        <span
                          className={cn(
                            "text-[10px] font-bold uppercase italic tracking-widest px-2 py-0.5 bg-white/[0.02] border border-white/5 rounded text-white/60",
                            row.isAccent ? "text-[#FF6B00]/80" : "",
                          )}
                        >
                          {row.value}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* 2. DROIDS */}
            {activeSegment === "droids" && (
              <div className="flex gap-8 h-full min-h-[600px] animate-in fade-in slide-in-from-bottom-2 duration-500 overflow-hidden">
                <div className="flex-1 space-y-10 overflow-y-auto pr-2 scrollbar-hide pb-20">
                  <div className="flex items-center justify-between sticky top-0 bg-[#080808]/80 backdrop-blur-md z-10 py-4 -mt-4">
                    <div className="space-y-1">
                      <h2 className="text-2xl font-black text-white uppercase tracking-tight italic">
                        Workforce configuration
                      </h2>
                      <p className="text-[11px] font-bold text-white/20 uppercase tracking-widest italic leading-relaxed">
                        Manage your active droids, roles, and capability mappings.
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button className="flex items-center gap-2 px-5 py-2.5 bg-white/5 border border-white/10 hover:border-white/20 text-[10px] font-black text-white/60 hover:text-white uppercase tracking-widest transition-all rounded-lg">
                        <CloudDownload className="h-4 w-4" /> Import Template
                      </button>
                      <button className="flex items-center gap-2 px-6 py-3 bg-[#FF6B00] text-black text-[11px] font-black uppercase tracking-widest hover:shadow-[0_0_25px_rgba(255,107,0,0.3)] rounded-lg transition-all group">
                        <Plus className="h-4 w-4 group-hover:rotate-90 transition-transform" />{" "}
                        Add Droid
                      </button>
                    </div>
                  </div>

                  <div className="bg-[#0c0c0c] border border-white/5 rounded-2xl overflow-hidden shadow-2xl">
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className="border-b border-white/5 bg-black/40">
                            <th className="px-6 py-4 text-[9px] font-black text-white/20 uppercase tracking-[0.3em]">
                              Identity_Kernel
                            </th>
                            <th className="px-6 py-4 text-[9px] font-black text-white/20 uppercase tracking-[0.3em]">
                              Runtime_Mapping
                            </th>
                            <th className="px-6 py-4 text-[9px] font-black text-white/20 uppercase tracking-[0.3em]">
                              State
                            </th>
                            <th className="px-6 py-4 text-right text-[9px] font-black text-white/20 uppercase tracking-[0.3em]">
                              Controls
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {agents.map((agent) => (
                            <tr
                              key={agent.id}
                              onClick={() => setSelectedAgentId(agent.id)}
                              className={cn(
                                "group hover:bg-white/[0.015] transition-colors cursor-pointer",
                                agent.id === selectedAgentId
                                  ? "bg-[#FF6B00]/[0.05] border-l-2 border-l-[#FF6B00]"
                                  : "border-l-2 border-l-transparent",
                              )}
                            >
                              <td className="px-6 py-6">
                                <div className="flex items-center gap-4">
                                  <div className="h-10 w-10 border border-white/10 rounded-xl overflow-hidden shrink-0 group-hover:border-[#FF6B00]/40 transition-colors bg-black">
                                    <img
                                      src={`https://picsum.photos/seed/${agent.name}/100/100`}
                                      className="w-full h-full object-cover opacity-60 group-hover:opacity-90 transition-opacity"
                                      referrerPolicy="no-referrer"
                                      alt=""
                                    />
                                  </div>
                                  <div className="flex flex-col">
                                    <span className="text-[12px] font-black text-white uppercase italic tracking-widest flex items-center gap-2">
                                      {agent.name}
                                      {agent.id === selectedAgentId && (
                                        <div className="h-1 w-1 rounded-full bg-[#FF6B00]" />
                                      )}
                                    </span>
                                    <span className="text-[9px] font-bold text-white/20 uppercase tracking-widest italic mt-0.5">
                                      {agent.role}
                                    </span>
                                  </div>
                                </div>
                              </td>
                              <td className="px-6 py-6">
                                <div className="space-y-3">
                                  <div className="flex items-center gap-3">
                                    <Brain className="h-3 w-3 text-[#FF6B00]" />
                                    <span className="text-[10px] font-bold text-white/60 uppercase tracking-widest">
                                      {agent.model}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-3">
                                    <ToyBrick className="h-3 w-3 text-white/20" />
                                    <span className="text-[10px] font-bold text-white/30 uppercase tracking-widest italic">
                                      {agent.assignedTools?.length || 0}{" "}
                                      Integrated Chips
                                    </span>
                                  </div>
                                </div>
                              </td>
                              <td className="px-6 py-6">
                                <div className="flex items-center gap-2.5">
                                  <div
                                    className={cn(
                                      "h-1.5 w-1.5 rounded-full",
                                      agent.keyConnected
                                        ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]"
                                        : "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]",
                                    )}
                                  />
                                  <div className="flex flex-col">
                                    <span
                                      className={cn(
                                        "text-[9px] font-black uppercase tracking-widest leading-none",
                                        agent.keyConnected
                                          ? "text-green-500/80"
                                          : "text-red-500/80",
                                      )}
                                    >
                                      {agent.keyConnected ? "Ready" : "Key Error"}
                                    </span>
                                    <span className="text-[8px] font-bold text-white/10 uppercase tracking-widest mt-1">
                                      Provider_Node_A
                                    </span>
                                  </div>
                                </div>
                              </td>
                              <td className="px-6 py-6">
                                <div className="flex items-center justify-end gap-1 opacity-20 group-hover:opacity-100 transition-opacity">
                                  <button
                                    title="Set Active"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedAgentId(agent.id);
                                    }}
                                    className={cn(
                                      "p-2 rounded-lg transition-all",
                                      agent.id === selectedAgentId
                                        ? "text-[#FF6B00] bg-[#FF6B00]/10"
                                        : "text-white/40 hover:text-[#FF6B00] hover:bg-white/5",
                                    )}
                                  >
                                    <Check className="h-4 w-4" />
                                  </button>
                                  <button
                                    title="Edit Details"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedAgentId(agent.id);
                                    }}
                                    className="p-2 text-white/40 hover:text-white hover:bg-white/5 rounded-lg transition-all"
                                  >
                                    <Edit2 className="h-4 w-4" />
                                  </button>
                                  <button
                                    title="Duplicate"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      // Logic handled in row selection or separate handler if available
                                    }}
                                    className="p-2 text-white/40 hover:text-white hover:bg-white/5 rounded-lg transition-all"
                                  >
                                    <Copy className="h-4 w-4" />
                                  </button>
                                  <div className="w-px h-4 bg-white/5 mx-1" />
                                  <button
                                    title="Remove"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                    }}
                                    className="p-2 text-white/40 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-all"
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div className="flex items-center justify-between px-4">
                    <div className="flex items-center gap-6">
                      <button className="text-[10px] font-black text-[#FF6B00] uppercase tracking-widest hover:underline underline-offset-4 transition-all">
                        Save Team Preset
                      </button>
                      <button className="text-[10px] font-black text-white/20 uppercase tracking-widest hover:text-white transition-all">
                        Bulk Actions
                      </button>
                    </div>
                    <span className="text-[9px] font-bold text-white/10 uppercase tracking-widest italic">
                      Syncing with remote workforce register...
                    </span>
                  </div>
                </div>

                {/* Droid Details Right Panel */}
                <div className="w-[400px] shrink-0 bg-[#0c0c0c] border border-white/5 rounded-3xl overflow-hidden flex flex-col shadow-2xl animate-in fade-in slide-in-from-right-4 duration-500">
                  <DroidConfigPanel />
                </div>
              </div>
            )}

            {/* REMAINING PLACEHOLDERS */}
            {["activity"].includes(activeSegment) && (
              <div className="space-y-12 animate-in fade-in slide-in-from-bottom-2 duration-500 max-w-4xl">
                <div className="space-y-2">
                  <div className="flex items-center gap-4">
                    <div className="px-3 py-1 bg-[#FF6B00]/10 border border-[#FF6B00]/20 rounded text-[9px] font-black text-[#FF6B00] uppercase tracking-widest italic shadow-[0_0_10px_rgba(255,107,0,0.1)]">
                      Staged for v3.0
                    </div>
                    <h3 className="text-3xl font-black text-white uppercase italic tracking-tighter">
                      {
                        sections
                          .flatMap((g) => g.items)
                          .find((i) => i.id === activeSegment)?.label
                      }
                    </h3>
                  </div>
                  <p className="text-[12px] font-bold text-white/20 uppercase tracking-widest italic leading-relaxed">
                    This operational surface is currently locked for review.
                    Advanced logic for{" "}
                    {sections
                      .flatMap((g) => g.items)
                      .find((i) => i.id === activeSegment)
                      ?.label.toLowerCase()}{" "}
                    is not yet available in the local kernel.
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="p-10 bg-[#0c0c0c] border border-white/5 rounded-3xl space-y-6 opacity-40 grayscale group hover:opacity-60 transition-all cursor-not-allowed">
                    <div className="h-10 w-10 bg-black/40 border border-white/5 rounded-xl flex items-center justify-center">
                      <Lock className="h-5 w-5 text-white/5" />
                    </div>
                    <div className="space-y-3">
                      <div className="h-5 w-40 bg-white/5 rounded italic" />
                      <div className="h-3 w-56 bg-white/5 rounded opacity-40 uppercase tracking-widest" />
                    </div>
                  </div>
                  <div className="p-10 bg-[#0c0c0c] border border-white/5 rounded-3xl space-y-6 opacity-40 grayscale group hover:opacity-60 transition-all cursor-not-allowed">
                    <div className="h-10 w-10 bg-black/40 border border-white/5 rounded-xl flex items-center justify-center">
                      <Lock className="h-5 w-5 text-white/5" />
                    </div>
                    <div className="space-y-3">
                      <div className="h-5 w-48 bg-white/5 rounded italic" />
                      <div className="h-3 w-64 bg-white/5 rounded opacity-40 uppercase tracking-widest" />
                    </div>
                  </div>
                </div>

                <div className="p-12 bg-[#FF6B00]/5 border border-[#FF6B00]/20 rounded-3xl relative overflow-hidden flex items-center gap-12 group">
                  <div className="h-24 w-24 rounded-[2rem] bg-black border border-[#FF6B00]/20 flex items-center justify-center shrink-0 group-hover:rotate-12 transition-transform duration-700 shadow-2xl">
                    <Zap className="h-10 w-10 text-[#FF6B00]/60" />
                  </div>
                  <div className="space-y-4">
                    <h4 className="text-lg font-black text-white uppercase italic tracking-widest leading-none">
                      Operational Honesty Protocol
                    </h4>
                    <p className="text-[13px] font-bold text-white/30 uppercase tracking-widest leading-relaxed">
                      HAM preserves the workbench layout above all else.
                      Sections like **Storage**, **Persona**, and **Activity
                      history** are being migrated to the new industrial
                      backend.
                    </p>
                  </div>
                  <div className="absolute top-0 right-0 h-full w-48 bg-gradient-to-l from-[#FF6B00]/10 to-transparent pointer-events-none" />
                </div>
              </div>
            )}
          </div>

          {/* Content Footer Status */}
          <div className="absolute bottom-0 inset-x-0 h-16 bg-black/60 border-t border-white/5 backdrop-blur-xl flex items-center px-10 justify-between">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]" />
                <span className="text-[9px] font-black font-mono text-green-500/60 uppercase tracking-widest">
                  Kernel Lifecycle: Online
                </span>
              </div>
              <div className="h-4 w-px bg-white/10" />
              <span className="text-[9px] font-black font-mono text-white/10 uppercase tracking-widest italic">
                Ready for mission directive
              </span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1 bg-white/5 rounded border border-white/10">
              <Command className="h-3 w-3 text-white/20" />
              <span className="text-[10px] font-black text-white/40 uppercase tracking-widest">
                ⌘ / ENTER to apply
              </span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
