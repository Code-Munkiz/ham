import * as React from "react";
import {
  Key,
  Globe,
  ToyBrick,
  Database,
  User,
  Bell,
  ShieldCheck,
  History,
  Activity,
  BarChart3,
  FileSearch,
  HardDrive,
  Cpu,
  Zap,
  Layout,
  Brain,
  Layers,
  Users,
  Box,
  Plus,
  RefreshCw,
  Edit2,
  Lock,
  Calendar,
  Puzzle,
  Package,
  Search,
  Eye,
  FileText,
  Workflow,
  CheckCircle2,
  SearchCode,
  Download,
  Settings2,
  UserPlus,
  Power,
  Terminal,
  Monitor,
  Shield,
  BookOpen,
  ListFilter,
  ArrowUpRight,
} from "lucide-react";

import { cn } from "@/lib/utils";

export type SettingsSubSectionId =
  | "api-keys"
  | "providers"
  | "tools-extensions"
  | "databases"
  | "account"
  | "notifications"
  | "security"
  | "context-memory"
  | "control-panel"
  | "mission-history"
  | "system-logs"
  | "diagnostics"
  | "kernel-health"
  | "context-audit"
  | "bridge-dump"
  | "workforce-profiles"
  | "resource-storage"
  | "jobs";

interface UnifiedSettingsProps {
  activeSubSegment: SettingsSubSectionId;
  onSubSegmentChange: (id: SettingsSubSectionId) => void;
  variant?: "overlay" | "page";
}

const settingsStructure = [
  {
    group: "Core Setup",
    items: [
      { id: "api-keys", label: "API Keys", icon: Key },
      { id: "providers", label: "Providers", icon: Globe },
      { id: "tools-extensions", label: "Tools, Skills & Extensions", icon: ToyBrick },
      { id: "databases", label: "Databases", icon: Database },
    ],
  },
  {
    group: "Workspace Preferences",
    items: [
      { id: "account", label: "Account", icon: User },
      { id: "notifications", label: "Notifications", icon: Bell },
      { id: "security", label: "Security", icon: ShieldCheck },
      { id: "context-memory", label: "Context & Memory", icon: Brain },
      { id: "control-panel", label: "Control Panel Preferences", icon: Layout },
    ],
  },
  {
    group: "Advanced",
    items: [
      { id: "mission-history", label: "Mission History", icon: History },
      { id: "system-logs", label: "System Logs", icon: Activity },
      { id: "diagnostics", label: "Diagnostics", icon: BarChart3 },
      { id: "kernel-health", label: "Kernel Health", icon: Zap },
      { id: "context-audit", label: "Context Audit", icon: FileSearch },
      { id: "bridge-dump", label: "Bridge Dump", icon: HardDrive },
      { id: "workforce-profiles", label: "Workforce Profiles", icon: Users },
      { id: "resource-storage", label: "Resource Storage", icon: Box },
      { id: "jobs", label: "Jobs", icon: Calendar },
    ],
  },
];

export function UnifiedSettings({
  activeSubSegment,
  onSubSegmentChange,
  variant = "overlay",
}: UnifiedSettingsProps) {
  const activeLabel = settingsStructure
    .flatMap((g) => g.items)
    .find((i) => i.id === activeSubSegment)?.label;

  return (
    <div className="flex h-full bg-[#050505] font-sans">
      {/* Internal Settings Sub-Nav */}
      <div className={cn(
        "w-64 border-r border-white/5 p-8 flex flex-col gap-10 overflow-y-auto shrink-0",
        variant === "page" ? "bg-transparent" : "bg-[#0c0c0c]"
      )}>
        {settingsStructure.map((group) => (
          <div key={group.group} className="space-y-4">
            <h4 className="px-3 text-[9px] font-black text-white/20 uppercase tracking-[0.4em] italic leading-none">
              {group.group}
            </h4>
            <div className="space-y-1">
              {group.items.map((item) => (
                <button
                  key={item.id}
                  onClick={() => onSubSegmentChange(item.id as SettingsSubSectionId)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all text-left group",
                    activeSubSegment === item.id
                      ? "bg-[#FF6B00]/10 text-[#FF6B00]"
                      : "text-white/30 hover:text-white hover:bg-white/[0.03]"
                  )}
                >
                  <item.icon
                    className={cn(
                      "h-3.5 w-3.5",
                      activeSubSegment === item.id
                        ? "text-[#FF6B00]"
                        : "text-white/20"
                    )}
                  />
                  <span className="text-[10px] font-black uppercase tracking-widest whitespace-nowrap">
                    {item.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Sub-Settings Content Area */}
      <div className="flex-1 overflow-y-auto p-12 pb-32 scrollbar-hide">
        <div className="space-y-12 animate-in fade-in slide-in-from-right-4 duration-500 max-w-4xl">
          {/* Section Header */}
          <div className="space-y-3 pb-8 border-b border-white/5">
            <h2 className="text-3xl font-black text-white uppercase italic tracking-tighter leading-none">
              {activeLabel}
            </h2>
            <p className="text-[11px] font-bold text-white/20 uppercase tracking-[0.2em] italic max-w-2xl">
              Industrial grade {activeSubSegment.replace("-", " ")} configuration for secure HAM operations.
            </p>
          </div>

          <div className="space-y-10">
            {/* --- CONFIGURATION PAGES --- */}
            {["api-keys", "providers", "tools-extensions", "databases", "security", "notifications", "context-memory"].includes(activeSubSegment) && (
              <div className="space-y-6">
                {activeSubSegment === "api-keys" && (
                  <div className="space-y-px bg-white/5 border border-white/5 rounded-lg overflow-hidden divide-y divide-white/5 shadow-2xl">
                    {[
                      { provider: "Gemini", status: "Verified", key: "AIzaSy...4rA", workers: 5 },
                      { provider: "Anthropic", status: "Active", key: "sk-ant-...v1p", workers: 2 },
                      { provider: "Custom Bridge", status: "Local", key: "127.0...902", workers: 1 },
                    ].map((item, idx) => (
                      <div key={idx} className="flex items-center justify-between p-5 bg-black/40 hover:bg-white/[0.04] transition-all group">
                        <div className="flex items-center gap-6">
                          <div className="h-10 w-10 bg-black border border-white/10 rounded flex items-center justify-center transition-colors group-hover:border-[#FF6B00]/40">
                            <Key className="h-5 w-5 text-white/10 group-hover:text-[#FF6B00] transition-colors" />
                          </div>
                          <div className="space-y-1">
                            <span className="text-[12px] font-black text-white uppercase tracking-widest leading-none block">{item.provider}</span>
                            <span className={cn(
                              "text-[8px] font-black uppercase italic tracking-widest",
                              item.status === 'Verified' ? "text-green-500/60" : item.status === 'Active' ? "text-blue-500/60" : "text-white/20"
                            )}>{item.status}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-10">
                          <code className="text-[10px] font-mono text-white/20 bg-black/60 px-3 py-1.5 rounded border border-white/5">{item.key}</code>
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button className="p-2 text-white/20 hover:text-white transition-colors" title="Rotate"><RefreshCw className="h-4 w-4" /></button>
                            <button className="p-2 text-white/20 hover:text-white transition-colors" title="Edit"><Edit2 className="h-4 w-4" /></button>
                          </div>
                        </div>
                      </div>
                    ))}
                    <button className="w-full flex items-center justify-center gap-3 py-5 bg-white/[0.01] hover:bg-white/[0.03] transition-all text-[#FF6B00]/40 hover:text-[#FF6B00]">
                      <Plus className="h-4 w-4" />
                      <span className="text-[10px] font-black uppercase tracking-widest leading-none">Connect Industrial Access Key</span>
                    </button>
                  </div>
                )}

                {activeSubSegment === "providers" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {[
                      { name: "Google Vertex", desc: "Enterprise-grade AI substrate with direct HAM kernel integration.", active: true },
                      { name: "Anthropic Claude", desc: "Advanced reasoning for complex extraction and droid logic.", active: true },
                      { name: "OpenAI Foundry", desc: "High-throughput processing for batch data bridge operations.", active: false },
                      { name: "Mistral Industrial", desc: "Local-first model support for privacy-locked secure units.", active: false },
                    ].map((p, i) => (
                      <div key={i} className="p-6 bg-black/40 border border-white/5 rounded-xl hover:bg-white/[0.02] transition-all group flex flex-col justify-between h-40 shadow-xl overflow-hidden relative">
                        <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                        <div className="flex items-center justify-between relative z-10">
                          <div className="flex items-center gap-3">
                             <Globe className="h-4 w-4 text-[#FF6B00]/40" />
                             <span className="text-[11px] font-black text-white uppercase tracking-widest">{p.name}</span>
                          </div>
                          <div className={cn("h-4 w-8 rounded-full border border-white/10 p-0.5", p.active ? "bg-[#FF6B00]/20" : "bg-white/5 transition-colors")}>
                            <div className={cn("h-2.5 w-2.5 rounded-full transition-all", p.active ? "bg-[#FF6B00] ml-auto" : "bg-white/10")} />
                          </div>
                        </div>
                        <p className="text-[10px] font-bold text-white/20 uppercase tracking-widest italic leading-relaxed relative z-10">{p.desc}</p>
                        <button className="text-[9px] font-black text-[#FF6B00]/40 uppercase tracking-widest hover:text-[#FF6B00] text-left relative z-10">Configure Parameters</button>
                      </div>
                    ))}
                  </div>
                )}

                {activeSubSegment === "tools-extensions" && (
                   <div className="space-y-16 animate-in fade-in slide-in-from-bottom-2 duration-500">
                      {/* Section 1: Built-in Tools */}
                      <div className="space-y-6">
                        <div className="flex items-center justify-between">
                          <div className="space-y-1">
                            <div className="flex items-center gap-3">
                              <ToyBrick className="h-4 w-4 text-[#FF6B00]" />
                              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">Built-in Tools</h3>
                            </div>
                            <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest leading-none pl-7">Core HAM operational capabilities</p>
                          </div>
                          <div className="h-px flex-1 mx-8 bg-white/5" />
                          <div className="flex items-center gap-3">
                             <span className="text-[8px] font-black text-white/10 uppercase tracking-widest">Active Pool: 6/7</span>
                             <div className="h-1 w-12 bg-white/5 rounded-full overflow-hidden">
                                <div className="h-full bg-[#FF6B00] w-[85%]" />
                             </div>
                          </div>
                        </div>
                        <div className="space-y-2">
                          {[
                            { name: "Code Interpreter", desc: "Execute sandboxed code in Python and JS environments.", status: "active", scope: "all droids", icon: Terminal, load: "High" },
                            { name: "Web Intelligence", desc: "Live web traversal and semantic extraction.", status: "active", scope: "selected droids", icon: Globe, load: "Nominal" },
                            { name: "Image Extraction", desc: "Multi-modal vision analysis for visual datasets.", status: "setup required", scope: "team only", icon: Zap, load: "Standby" },
                            { name: "Browser", desc: "Autonomous browser orchestration for task completion.", status: "active", scope: "all droids", icon: Monitor, load: "Idle" },
                            { name: "Preview", desc: "Real-time rendering of generated artifacts and code.", status: "active", scope: "all droids", icon: Eye, load: "Idle" },
                            { name: "Search", desc: "Industrial-grade index searching across global networks.", status: "inactive", scope: "team only", icon: Search, load: "Locked" },
                            { name: "Workspace Context", desc: "High-density local knowledge indexing.", status: "active", scope: "all droids", icon: Brain, load: "Syncing" },
                          ].map((tool, i) => (
                            <div key={i} className="group flex items-center gap-6 p-4 bg-black/40 border border-white/5 rounded-xl hover:border-[#FF6B00]/20 transition-all shadow-lg relative overflow-hidden">
                              <div className="absolute top-0 left-0 w-1 h-full bg-[#FF6B00] opacity-0 group-hover:opacity-100 transition-opacity" />
                              <div className="h-10 w-10 shrink-0 bg-white/[0.03] rounded border border-white/5 flex items-center justify-center group-hover:bg-[#FF6B00]/10 transition-colors">
                                <tool.icon className="h-4 w-4 text-[#FF6B00]" />
                              </div>
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] font-black text-white uppercase tracking-widest truncate">{tool.name}</span>
                                  <div className={cn(
                                    "px-1.5 py-0.5 rounded-[2px] text-[7px] font-black uppercase tracking-tighter",
                                    tool.status === 'active' ? "bg-green-500/10 text-green-500 border border-green-500/20" : 
                                    tool.status === 'setup required' ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" : 
                                    "bg-white/5 text-white/20 border border-white/10"
                                  )}>
                                    {tool.status}
                                  </div>
                                </div>
                                <p className="text-[9px] font-bold text-white/40 uppercase tracking-widest truncate italic leading-none">{tool.desc}</p>
                              </div>
                              <div className="hidden md:flex flex-col items-center gap-1 px-4 border-l border-white/5 min-w-[100px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Load State</span>
                                <span className="text-[9px] font-mono font-bold text-[#FF6B00]/60 uppercase tracking-tighter italic">{tool.load}</span>
                              </div>
                              <div className="hidden md:flex flex-col items-end gap-1 px-4 border-l border-white/5 min-w-[120px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Assignment</span>
                                <span className="text-[9px] font-black text-white/40 uppercase tracking-tighter italic whitespace-nowrap">{tool.scope}</span>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Assign</button>
                                <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Configure</button>
                                <button className="h-8 px-3 rounded bg-[#FF6B00]/10 border border-[#FF6B00]/20 text-[9px] font-black text-[#FF6B00] uppercase tracking-widest hover:bg-[#FF6B00]/20 transition-all">
                                  {tool.status === 'active' ? "Disable" : "Enable"}
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Section 2: Skills & Behaviors */}
                      <div className="space-y-6">
                        <div className="flex items-center justify-between">
                          <div className="space-y-1">
                            <div className="flex items-center gap-3">
                              <Puzzle className="h-4 w-4 text-[#FF6B00]" />
                              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">Skills & Behaviors</h3>
                            </div>
                            <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest leading-none pl-7">Unit-specific capabilities and workforce roles</p>
                          </div>
                          <div className="h-px flex-1 mx-8 bg-white/5" />
                        </div>
                        <div className="space-y-2">
                          {[
                            { name: "Reviewer", cat: "Quality Control", desc: "Autonomous audit of code and document integrity.", status: "enabled", assigned: "Core Droid Group", icon: CheckCircle2 },
                            { name: "Researcher", cat: "Intelligence", desc: "Deep-dive data aggregation and verification.", status: "enabled", assigned: "Alpha Team", icon: Search },
                            { name: "QA", cat: "Quality Control", desc: "Automated regression and stability testing.", status: "disabled", assigned: "Unassigned", icon: Shield },
                            { name: "Planning", cat: "Orchestration", desc: "Long-horizon task decomposition and scheduling.", status: "enabled", assigned: "Command Unit", icon: Workflow },
                            { name: "Documentation", cat: "Linguistics", desc: "Synthesizing technical specs from codebase deltas.", status: "enabled", assigned: "Linguistics Cluster", icon: FileText },
                            { name: "Retrieval", cat: "Intelligence", desc: "Context-aware lookup across disparate bridge files.", status: "enabled", assigned: "Storage Node", icon: Box },
                            { name: "Code Audit", cat: "Security", desc: "Vulnerability scanning and logic-leak detection.", status: "disabled", assigned: "Unassigned", icon: SearchCode },
                          ].map((skill, i) => (
                            <div key={i} className="group flex items-center gap-6 p-4 bg-black/40 border border-white/5 rounded-xl hover:border-white/20 transition-all relative overflow-hidden">
                              <div className="h-10 w-10 shrink-0 bg-white/[0.03] rounded border border-white/5 flex items-center justify-center">
                                <skill.icon className="h-4 w-4 text-white/40 group-hover:text-[#FF6B00] transition-colors" />
                              </div>
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center gap-3">
                                  <span className="text-[11px] font-black text-white uppercase tracking-widest truncate">{skill.name}</span>
                                  <span className="text-[8px] font-bold text-white/10 uppercase tracking-[0.2em] italic bg-white/5 px-1.5 py-0.5 rounded-[2px]">{skill.cat}</span>
                                </div>
                                <p className="text-[9px] font-bold text-white/30 uppercase tracking-widest truncate italic leading-none">{skill.desc}</p>
                              </div>
                              <div className="hidden lg:flex flex-col items-end gap-1 px-4 border-l border-white/5 min-w-[150px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Linked Unit</span>
                                <span className="text-[9px] font-black text-white/40 uppercase tracking-tighter italic truncate w-full text-right">{skill.assigned}</span>
                              </div>
                              <div className="flex items-center gap-4 shrink-0 px-4 border-l border-white/5">
                                <div className="flex flex-col gap-1">
                                  <button className="h-7 px-3 rounded bg-white/[0.03] border border-white/5 text-[8px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Assign</button>
                                  <button className="h-7 px-3 rounded bg-white/[0.03] border border-white/5 text-[8px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Requirements</button>
                                </div>
                                <div className={cn(
                                  "h-8 w-12 rounded cursor-pointer border flex items-center px-1 transition-all",
                                  skill.status === 'enabled' ? "bg-green-500/10 border-green-500/30" : "bg-white/5 border-white/10"
                                )}>
                                  <div className={cn(
                                    "h-6 w-5 rounded-sm transition-all shadow-sm",
                                    skill.status === 'enabled' ? "bg-green-500 ml-auto" : "bg-white/20"
                                  )} />
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Section 3: Extensions & Plugins */}
                      <div className="space-y-6">
                        <div className="flex items-center justify-between">
                          <div className="space-y-1">
                            <div className="flex items-center gap-3">
                              <Package className="h-4 w-4 text-[#FF6B00]" />
                              <h3 className="text-[14px] font-black text-white uppercase tracking-[0.2em] italic leading-none">Extensions & Plugins</h3>
                            </div>
                            <p className="text-[10px] font-bold text-white/20 uppercase tracking-widest leading-none pl-7">3rd party integrations and modular enhancements</p>
                          </div>
                          <div className="flex items-center gap-3 ml-8">
                             <div className="h-px w-24 bg-white/5" />
                             <button className="flex items-center gap-2 px-3 py-1.5 rounded border border-[#FF6B00]/20 bg-[#FF6B00]/5 text-[#FF6B00] hover:bg-[#FF6B00]/10 transition-all group">
                                <Plus className="h-3 w-3" />
                                <span className="text-[9px] font-black uppercase tracking-widest italic leading-none">Add Extension</span>
                             </button>
                             <div className="h-px flex-1 bg-white/5" />
                          </div>
                        </div>
                        <div className="space-y-2">
                          {[
                            { name: "Mercury UI Tab", type: "UI Interface", installed: true, enabled: true, desc: "Custom operational surface for high-frequency trading data.", icon: Layout, version: "v1.2.4" },
                            { name: "Azure Bridge", type: "Provider Integration", installed: true, enabled: false, desc: "Connects HAM units to Azure Cloud Service endpoints.", icon: Database, version: "v0.9.8" },
                            { name: "Slack Bridge", type: "Social Hub", installed: false, enabled: false, desc: "Bidirectional workspace communication pipeline.", icon: RefreshCw, version: "v2.1.0" },
                            { name: "Auth Bundle", type: "Security Extension", installed: true, enabled: true, desc: "Advanced OAuth and JWT validation logic.", icon: Lock, version: "v4.0.1" },
                          ].map((ext, i) => (
                            <div key={i} className="group flex items-center gap-6 p-4 bg-black/40 border border-white/5 rounded-xl hover:bg-white/[0.02] transition-all relative overflow-hidden">
                              <div className="h-10 w-10 shrink-0 border border-white/5 rounded bg-white/[0.02] flex items-center justify-center opacity-40 group-hover:opacity-100 transition-opacity">
                                <ext.icon className="h-4 w-4 text-white" />
                              </div>
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-[11px] font-black text-white uppercase tracking-widest">{ext.name}</span>
                                  <span className="text-[8px] font-bold text-[#FF6B00]/60 uppercase tracking-widest italic px-1.5 py-0.5 rounded-[2px] bg-[#FF6B00]/5 border border-[#FF6B00]/10">{ext.type}</span>
                                </div>
                                <p className="text-[9px] font-bold text-white/20 uppercase tracking-widest truncate italic leading-none">{ext.desc}</p>
                              </div>
                              <div className="hidden md:flex flex-col items-center gap-1 px-4 border-l border-white/5 min-w-[80px]">
                                <span className="text-[7px] font-black text-white/10 uppercase tracking-widest">Version</span>
                                <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-tighter italic">{ext.version}</span>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                {!ext.installed ? (
                                  <button className="h-8 px-4 rounded bg-[#FF6B00] text-[9px] font-black text-black uppercase tracking-widest hover:bg-[#FF8533] transition-all flex items-center gap-2">
                                    <Download className="h-3 w-3" />
                                    <span>Install</span>
                                  </button>
                                ) : (
                                  <>
                                    <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all flex items-center gap-2">
                                       <ArrowUpRight className="h-3 w-3" />
                                       <span>Open</span>
                                    </button>
                                    <button className="h-8 px-3 rounded bg-white/[0.03] border border-white/5 text-[9px] font-black text-white/40 uppercase tracking-widest hover:bg-white/10 hover:text-white transition-all">Configure</button>
                                    <button className={cn(
                                      "h-8 px-4 rounded text-[9px] font-black uppercase tracking-widest transition-all",
                                      ext.enabled ? "bg-[#FF6B00]/10 border border-[#FF6B00]/20 text-[#FF6B00]" : "bg-white/5 border border-white/10 text-white/20"
                                    )}>
                                      {ext.enabled ? "Disable" : "Enable"}
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                   </div>
                )}

                {activeSubSegment === "security" && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div className="p-10 bg-black/40 border border-white/5 space-y-8 rounded-xl shadow-xl">
                      <div className="flex items-center gap-4">
                        <div className="h-10 w-10 bg-[#FF6B00]/10 border border-[#FF6B00]/20 rounded flex items-center justify-center">
                          <ShieldCheck className="h-5 w-5 text-[#FF6B00]" />
                        </div>
                        <h4 className="text-[12px] font-black uppercase tracking-[0.3em] text-white italic">Identity Lockdown</h4>
                      </div>
                      <div className="space-y-3">
                        {[
                          { label: "Hardware Key Sync", status: "Secure", active: true },
                          { label: "MFA Tunneling", status: "Active", active: true },
                          { label: "Biometric Bridge", status: "Standby", active: false },
                        ].map((row, i) => (
                          <div key={i} className="flex items-center justify-between p-4 bg-white/[0.02] border border-white/5">
                            <span className="text-[10px] font-bold text-white/30 uppercase tracking-widest">{row.label}</span>
                            <span className={cn(
                              "text-[9px] font-black uppercase italic tracking-widest",
                              row.active ? "text-green-500/60" : "text-white/10"
                            )}>{row.status}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="p-10 bg-black/40 border border-white/5 space-y-8 rounded-xl flex flex-col justify-between shadow-xl relative overflow-hidden group">
                      <div className="absolute top-0 right-0 w-32 h-32 bg-[#FF6B00]/5 rounded-bl-full -mr-10 -mt-10 group-hover:bg-[#FF6B00]/10 transition-colors" />
                      <div className="space-y-4 relative z-10">
                        <div className="flex items-center gap-4">
                          <Lock className="h-5 w-5 text-[#FF6B00]" />
                          <h4 className="text-[12px] font-black uppercase tracking-[0.3em] text-white italic">Key Rotation</h4>
                        </div>
                        <p className="text-[11px] font-bold text-white/20 uppercase tracking-widest italic leading-relaxed">
                          Enforce system-wide rotation protocols across all connections to prevent bridge leakage.
                        </p>
                      </div>
                      <button className="w-full py-4 bg-white/5 border border-white/10 hover:border-[#FF6B00]/40 text-[10px] font-black text-white/40 hover:text-white uppercase tracking-[0.3em] transition-all rounded italic relative z-10">
                        Initiate Global Rotation
                      </button>
                    </div>
                  </div>
                )}

                {activeSubSegment === "context-memory" && (
                  <div className="space-y-6">
                    <div className="p-8 bg-black/40 border border-white/5 shadow-2xl space-y-8 rounded-xl overflow-hidden relative">
                      <div className="flex items-center justify-between relative z-10">
                        <div className="space-y-1">
                          <h4 className="text-[12px] font-black text-white uppercase italic tracking-widest">Context Budget Monitor</h4>
                          <p className="text-[10px] font-bold text-white/20 uppercase tracking-widest italic leading-relaxed">Optimization threshold for active workforce sessions.</p>
                        </div>
                        <div className="h-6 w-11 bg-[#FF6B00] rounded-full p-1 relative cursor-pointer shadow-[0_0_15px_rgba(255,107,0,0.3)]">
                          <div className="h-4 w-4 bg-black rounded-full ml-auto" />
                        </div>
                      </div>
                      <div className="pt-8 border-t border-white/5 space-y-6 relative z-10">
                        <div className="flex justify-between text-[11px] font-black uppercase tracking-widest text-white/40 leading-none">
                          <span>Max Context Window</span>
                          <span className="text-white italic">1.28M Tokens</span>
                        </div>
                        <div className="h-3 bg-white/5 rounded-full overflow-hidden border border-white/10">
                          <div className="h-full bg-[#FF6B00] w-[42%] shadow-[0_0_20px_#FF6B00]" />
                        </div>
                        <p className="text-[9px] font-black text-[#FF6B00]/40 uppercase tracking-[0.2em] italic">Current Session Intake: 537,600 tokens utilized</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* --- HEALTH / STATUS PAGES --- */}
            {["kernel-health", "diagnostics"].includes(activeSubSegment) && (
              <div className="space-y-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                   {[
                      { label: "Kernel Version", value: "2.5.0-HAM", status: "Operational", trend: "Stable" },
                      { label: "Active Workers", value: "154 Units", status: "Optimal", trend: "Nominal" },
                      { label: "Bridge Latency", value: "12ms", status: "Accelerated", trend: "High Speed" },
                      { label: "Memory Pressure", value: "14%", status: "Safe", trend: "Liquid Content" },
                      { label: "Provider Sync", value: "3/3 Active", status: "Aligned", trend: "Synchronized" },
                      { label: "Resource Load", value: "48%", status: "Balanced", trend: "Managed" },
                   ].map((metric, i) => (
                      <div key={i} className="p-6 bg-[#0c0c0c] border border-white/5 rounded-xl space-y-4 hover:border-white/20 transition-all">
                         <div className="flex justify-between items-start">
                            <span className="text-[10px] font-black text-white/20 uppercase tracking-widest leading-none">{metric.label}</span>
                            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]" />
                         </div>
                         <div className="space-y-1">
                            <div className="text-xl font-black text-white italic tracking-tighter leading-none">{metric.value}</div>
                            <div className="flex items-center gap-2">
                               <span className="text-[9px] font-black text-[#FF6B00] uppercase italic tracking-widest">{metric.status}</span>
                               <span className="text-[8px] font-bold text-white/10 uppercase tracking-widest">{metric.trend}</span>
                            </div>
                         </div>
                      </div>
                   ))}
                </div>

                <div className="p-10 bg-black/40 border border-white/10 rounded-2xl relative overflow-hidden group">
                   <div className="absolute inset-0 bg-gradient-to-r from-[#FF6B00]/5 to-transparent skew-x-12 -translate-x-full group-hover:translate-x-full transition-transform duration-[2000ms] ease-in-out" />
                   <div className="space-y-6 relative z-10 text-center">
                      <div className="h-1 w-1 bg-[#FF6B00] mx-auto rounded-full" />
                      <div className="space-y-2">
                         <h4 className="text-[12px] font-black text-white uppercase italic tracking-[0.4em]">Run Deep Sector Scan</h4>
                         <p className="text-[10px] font-bold text-white/20 uppercase tracking-[0.2em] italic max-w-sm mx-auto leading-relaxed">Initiate a full-system audit of all workforce bridge connections and memory registers.</p>
                      </div>
                      <button className="px-10 py-3 bg-[#FF6B00]/10 border border-[#FF6B00]/40 text-[10px] font-black text-[#FF6B00] uppercase tracking-[0.3em] italic hover:bg-[#FF6B00] hover:text-black transition-all rounded shadow-xl">Start System Diagnostics</button>
                   </div>
                </div>
              </div>
            )}

            {/* --- HISTORY / AUDIT PAGES --- */}
            {["mission-history", "system-logs", "context-audit", "bridge-dump"].includes(activeSubSegment) && (
              <div className="space-y-8 animate-in fade-in slide-in-from-left-4 duration-700">
                <div className="flex items-center justify-between px-6 py-4 bg-white/[0.02] border border-white/10 rounded-xl">
                   <div className="flex items-center gap-4">
                      <History className="h-4 w-4 text-[#FF6B00]" />
                      <span className="text-[11px] font-black text-white uppercase tracking-widest italic">Live Audit Stream</span>
                   </div>
                   <div className="flex items-center gap-4">
                      <div className="flex items-center gap-2 px-3 py-1 bg-black/40 border border-white/5 rounded text-[9px] font-black text-white/20 uppercase tracking-widest">
                         <FileSearch className="h-3 w-3" /> Filter Log Level
                      </div>
                      <div className="text-[9px] font-black text-[#FF6B00] uppercase tracking-widest underline underline-offset-4 cursor-pointer">Export Payload</div>
                   </div>
                </div>

                <div className="bg-[#0c0c0c] border border-white/5 rounded-xl divide-y divide-white/5 overflow-hidden shadow-2xl">
                   {[
                      { time: "05:12:04", action: "BRIDGE_RE_SYNC", actor: "Kernel", result: "COMPLETE", detail: "Rotated 154 worker heartbeat keys." },
                      { time: "05:10:55", action: "MEMORY_FLUSH", actor: "System", result: "NOMINAL", detail: "Purged 3.4GB of stale cache registers." },
                      { time: "05:08:21", action: "ID_VERIFY", actor: "Security", result: "SECURE", detail: "Verified user ham-admin82 through biometric bridge." },
                      { time: "05:04:12", action: "UNIT_REALLOCATE", actor: "Kernel", result: "ALIGNED", detail: "Moved 4 units from extraction to logic core." },
                      { time: "04:59:33", action: "TOOL_CALIBRATE", actor: "Chipset", result: "ACCELERATED", detail: "Optimized Code Interpreter for v3 architecture." },
                   ].map((log, i) => (
                      <div key={i} className="flex grid grid-cols-12 gap-8 items-center px-8 py-6 hover:bg-white/[0.02] transition-colors group">
                         <div className="col-span-1 text-[10px] font-mono text-white/20 whitespace-nowrap">{log.time}</div>
                         <div className="col-span-3 text-[11px] font-black text-[#FF6B00]/80 uppercase italic tracking-widest leading-none group-hover:text-[#FF6B00] transition-colors">{log.action}</div>
                         <div className="col-span-2 text-[9px] font-black text-white/20 uppercase tracking-[0.2em]">{log.actor}</div>
                         <div className="col-span-4 text-[11px] font-bold text-white/40 italic leading-relaxed">{log.detail}</div>
                         <div className="col-span-2 text-right">
                            <span className="text-[10px] font-black px-3 py-1 rounded-full bg-green-500/10 border border-green-500/20 text-green-500/60 uppercase">{log.result}</span>
                         </div>
                      </div>
                   ))}
                </div>
              </div>
            )}

            {/* --- JOBS / OTHERS --- */}
            {activeSubSegment === "jobs" && (
               <div className="space-y-8">
                  <div className="p-12 bg-black/40 border border-[#FF6B00]/20 border-dashed rounded-3xl flex flex-col items-center justify-center text-center space-y-8 animate-in zoom-in-95 duration-700">
                     <div className="h-20 w-20 bg-black/60 border border-white/5 rounded-full flex items-center justify-center relative group overflow-hidden">
                        <div className="absolute inset-0 bg-[#FF6B00]/2 animate-pulse" />
                        <Calendar className="h-8 w-8 text-white/10 relative z-10" />
                     </div>
                     <div className="space-y-3 relative z-10">
                        <h3 className="text-xl font-black text-white uppercase italic tracking-[0.3em]">SCHEDULER_OFFLINE</h3>
                        <p className="text-[11px] font-bold text-white/20 uppercase tracking-[0.2em] max-w-sm mx-auto leading-relaxed italic">The automated task scheduler is currently set to manual override. Scheduled jobs will be surfaced here in HAM v3.2.</p>
                     </div>
                     <button className="px-10 py-3 bg-white/5 border border-white/10 text-[10px] font-black text-white/20 uppercase tracking-widest rounded transition-all hover:bg-white/10 hover:text-white group">
                        Define Cron Directive <Plus className="ml-2 h-3.5 w-3.5 inline group-hover:text-[#FF6B00] transition-colors" />
                     </button>
                  </div>
               </div>
            )}

            {/* General Placeholder for everything else */}
            {!["api-keys", "providers", "tools-extensions", "security", "context-memory", "kernel-health", "diagnostics", "mission-history", "system-logs", "context-audit", "bridge-dump", "jobs"].includes(activeSubSegment) && (
              <div className="space-y-10">
                <div className="p-16 bg-black/20 border border-white/5 border-dashed rounded-2xl flex flex-col items-center justify-center text-center space-y-8 group transition-all hover:bg-black/40">
                  <div className="h-16 w-16 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-center transition-transform group-hover:scale-110">
                    <Zap className="h-6 w-6 text-white/10 group-hover:text-[#FF6B00]" />
                  </div>
                  <div className="space-y-3">
                    <h3 className="text-lg font-black text-white/40 uppercase italic tracking-[0.3em] group-hover:text-white transition-colors leading-none">calibration_active</h3>
                    <p className="text-[11px] font-bold text-white/10 group-hover:text-white/20 uppercase tracking-[0.4em] max-w-sm mx-auto transition-colors leading-relaxed">
                      The {activeLabel} subsystem is currently being optimized for high-throughput bridge operations.
                    </p>
                  </div>
                  <div className="flex items-center gap-3 opacity-40">
                    <div className="h-1.5 w-1.5 rounded-full bg-[#FF6B00] animate-pulse" />
                    <span className="text-[9px] font-black text-white/20 uppercase tracking-[0.5em]">awaiting telemetry</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
