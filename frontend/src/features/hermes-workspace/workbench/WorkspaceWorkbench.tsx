/**
 * HAM-native command-center workbench (right pane on /workspace/chat).
 * Placeholders and disabled actions only — no fake GitHub, preview, publish, or storage behavior.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Database,
  Eye,
  FileCode,
  FolderOpen,
  MoreHorizontal,
  Plus,
  Send,
  Settings2,
  Share2,
  Terminal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ProjectSourceIntakeDialog } from "./ProjectSourceIntakeDialog";

export type WorkspaceWorkbenchTabId =
  | "preview"
  | "code"
  | "database"
  | "storage"
  | "terminal"
  | "settings";

const TABS: Array<{ id: WorkspaceWorkbenchTabId; label: string; icon: typeof Eye }> = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "code", label: "Code", icon: FileCode },
  { id: "database", label: "Database", icon: Database },
  { id: "storage", label: "File storage", icon: FolderOpen },
  { id: "terminal", label: "Terminal", icon: Terminal },
  { id: "settings", label: "Settings", icon: Settings2 },
];

export function WorkspaceWorkbench() {
  const [activeTab, setActiveTab] = React.useState<WorkspaceWorkbenchTabId>("preview");
  const [projectSourceOpen, setProjectSourceOpen] = React.useState(false);

  return (
    <aside
      data-testid="hww-workbench"
      className={cn(
        "flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden",
        "border-white/[0.08] bg-[#040d14]/92 shadow-[inset_1px_0_0_0_rgba(255,255,255,0.04)]",
        "border-t md:border-t-0 md:border-l",
      )}
      aria-label="Workspace workbench"
    >
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/[0.08] px-2.5 py-2">
        <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto [scrollbar-width:thin]">
          {TABS.map((tab) => {
            const active = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                data-testid={`hww-workbench-tab-${tab.id}`}
                data-active={active ? "true" : "false"}
                onClick={() => {
                  setActiveTab(tab.id);
                }}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors",
                  active
                    ? "bg-white/[0.1] text-[#e8eef8]"
                    : "text-white/45 hover:bg-white/[0.06] hover:text-white/75",
                )}
                title={tab.label}
              >
                <Icon className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} aria-hidden />
                <span className="hidden sm:inline">{tab.label}</span>
              </button>
            );
          })}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled
            className="h-8 gap-1 px-2 text-[11px] text-white/35"
            title="Sharing is not available in this build"
            data-testid="hww-workbench-share"
          >
            <Share2 className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
            <span className="hidden lg:inline">Share</span>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled
            className="h-8 gap-1 px-2 text-[11px] text-white/35"
            title="Publish is not available in this build"
            data-testid="hww-workbench-publish"
          >
            <Send className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
            <span className="hidden lg:inline">Publish</span>
          </Button>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-8 w-8 p-0 text-white/55 hover:text-white/90"
                aria-label="More workbench actions"
                data-testid="hww-workbench-more"
              >
                <MoreHorizontal className="h-4 w-4" strokeWidth={1.5} aria-hidden />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                className="z-50 min-w-[12rem] rounded-lg border border-white/[0.1] bg-[#07141c] p-1 text-[11px] text-white/88 shadow-xl"
                sideOffset={6}
                align="end"
              >
                <DropdownMenu.Item
                  disabled
                  className="cursor-not-allowed rounded px-2 py-1.5 text-white/40 outline-none"
                >
                  Download ZIP — Coming soon
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  disabled
                  className="cursor-not-allowed rounded px-2 py-1.5 text-white/40 outline-none"
                >
                  Version history — Coming soon
                </DropdownMenu.Item>
                <DropdownMenu.Item
                  disabled
                  className="cursor-not-allowed rounded px-2 py-1.5 text-white/40 outline-none"
                >
                  Make a copy — Coming soon
                </DropdownMenu.Item>
                <DropdownMenu.Item asChild className="rounded outline-none">
                  <a
                    href="https://github.com/Code-Munkiz/ham/blob/main/README.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block px-2 py-1.5 text-[#7dd3fc] hover:bg-white/[0.06]"
                  >
                    View docs (GitHub)
                  </a>
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </div>

      <div
        data-testid={`hww-workbench-panel-${activeTab}`}
        className="hww-scroll min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-3"
      >
        {activeTab === "preview" ? <WorkbenchPreviewPanel /> : null}
        {activeTab === "code" ? (
          <WorkbenchCodePanel onAddProjectSource={() => setProjectSourceOpen(true)} />
        ) : null}
        {activeTab === "database" ? <WorkbenchDatabasePanel /> : null}
        {activeTab === "storage" ? (
          <WorkbenchStoragePanel onAddProjectSource={() => setProjectSourceOpen(true)} />
        ) : null}
        {activeTab === "terminal" ? <WorkbenchTerminalPanel /> : null}
        {activeTab === "settings" ? <WorkbenchSettingsPanel /> : null}
      </div>
      <ProjectSourceIntakeDialog open={projectSourceOpen} onOpenChange={setProjectSourceOpen} />
    </aside>
  );
}

function MutedPanel({ children }: { children: React.ReactNode }) {
  return <div className="space-y-3 text-[12px] leading-relaxed text-white/70">{children}</div>;
}

function WorkbenchPreviewPanel() {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">No preview yet.</p>
      <p className="text-white/55">
        Ask HAM to build or connect a project to generate a preview. Live site preview is not wired
        in this shell.
      </p>
    </MutedPanel>
  );
}

function AddProjectSourceButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      className="gap-1.5 text-[11px]"
      data-testid="hww-add-project-source"
      onClick={onClick}
    >
      <Plus className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
      Add project source
    </Button>
  );
}

function WorkbenchCodePanel({ onAddProjectSource }: { onAddProjectSource: () => void }) {
  return (
    <MutedPanel>
      <div className="flex flex-wrap items-center gap-2">
        <AddProjectSourceButton onClick={onAddProjectSource} />
      </div>
      <div className="grid min-h-[180px] gap-2 rounded-lg border border-white/[0.08] bg-black/25 md:grid-cols-2">
        <div className="border-b border-white/[0.06] p-2 md:border-b-0 md:border-r md:border-white/[0.06]">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Files</p>
          <p className="mt-2 text-white/45">Explorer placeholder — no repo mounted.</p>
        </div>
        <div className="p-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-white/40">Viewer</p>
          <p className="mt-2 text-white/45">Select a file to view source (not connected).</p>
        </div>
      </div>
      <p className="text-white/55">
        Use <span className="font-medium text-white/65">Add project source</span> to upload to your
        local workspace (when configured) or attach a file for chat. Open the{" "}
        <Link
          to="/workspace/files"
          className="font-medium text-[#7dd3fc] underline-offset-2 hover:underline"
        >
          Files
        </Link>{" "}
        route to browse disk after uploads. Full project intake and automatic repo import are not
        connected here yet.
      </p>
    </MutedPanel>
  );
}

function WorkbenchDatabasePanel() {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">Database</p>
      <p className="text-white/55">
        Connect a database to inspect schema, tables, and app data. Examples you might use later:
        Supabase, Neon, Firebase, BigQuery, Postgres. Connection flows are not available in this
        placeholder.
      </p>
    </MutedPanel>
  );
}

function WorkbenchStoragePanel({ onAddProjectSource }: { onAddProjectSource: () => void }) {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">File storage</p>
      <p className="text-white/55">
        No cloud project blob store yet. Use{" "}
        <span className="font-medium text-white/65">Add project source</span> for local workspace
        uploads (local API) or chat attachments. ZIP ingestion is not supported.
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        <AddProjectSourceButton onClick={onAddProjectSource} />
        <Button type="button" size="sm" variant="secondary" disabled className="text-[11px]">
          Upload ZIP — Coming soon
        </Button>
      </div>
    </MutedPanel>
  );
}

function WorkbenchTerminalPanel() {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">Terminal</p>
      <p className="text-white/55">
        Terminal is available from the workspace tools. Full embedded terminal in this pane is
        coming soon.
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        <Button type="button" size="sm" variant="secondary" asChild className="text-[11px]">
          <Link to="/workspace/terminal" data-testid="hww-workbench-terminal-open">
            Open terminal route
          </Link>
        </Button>
      </div>
    </MutedPanel>
  );
}

function SettingsLinkRow({ title, subtitle, to }: { title: string; subtitle: string; to: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-black/20 px-3 py-2.5">
      <p className="text-[12px] font-medium text-white/85">{title}</p>
      <p className="mt-1 text-[11px] text-white/45">{subtitle}</p>
      <Link
        to={to}
        className="mt-2 inline-flex text-[11px] font-medium text-[#7dd3fc] underline-offset-2 hover:underline"
      >
        Open in settings →
      </Link>
    </div>
  );
}

function WorkbenchSettingsPanel() {
  return (
    <MutedPanel>
      <p className="text-[13px] font-medium text-white/88">Settings</p>
      <p className="text-white/55">
        Full settings live in the workspace Settings app. Links below open the real routes — no
        duplicate persistence here.
      </p>
      <div className="grid gap-2 pt-1">
        <SettingsLinkRow
          title="General"
          subtitle="Display bundle and workspace-facing toggles."
          to="/workspace/settings?section=display"
        />
        <SettingsLinkRow
          title="Model / provider"
          subtitle="Models, API routing, and provider configuration."
          to="/workspace/settings?section=hermes"
        />
        <SettingsLinkRow
          title="System instructions"
          subtitle="Agent behavior and instruction surfaces."
          to="/workspace/settings?section=agent"
        />
        <SettingsLinkRow
          title="Connected tools"
          subtitle="Integrations and tool allowlists."
          to="/workspace/settings?section=tools"
        />
        <SettingsLinkRow
          title="Secrets"
          subtitle="Keys and environment configuration (managed in Settings)."
          to="/workspace/settings?section=connection"
        />
        <SettingsLinkRow
          title="GitHub"
          subtitle="Use Connected Tools for Git-related integration."
          to="/workspace/settings?section=tools"
        />
        <div className="rounded-lg border border-white/[0.06] bg-black/20 px-3 py-2.5">
          <p className="text-[12px] font-medium text-white/85">Usage</p>
          <p className="mt-1 text-[11px] text-white/45">
            Usage reporting is not surfaced in this workbench yet.
          </p>
        </div>
      </div>
    </MutedPanel>
  );
}
