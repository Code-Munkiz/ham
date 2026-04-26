import * as React from "react";
import { Construction } from "lucide-react";
import type { UpstreamSettingsNavId } from "./workspaceSettingsNavData";

/** repomix `src/routes/settings/index.tsx` switches on `section` for Hermes sub-views and appearance; HAM bridges where not wired. */

const COPY: Record<UpstreamSettingsNavId, { title: string; body: string }> = {
  connection: {
    title: "Connection",
    body: "Handled in the Connection section.",
  },
  hermes: { title: "Model & Provider", body: "Use the Model & provider section." },
  agent: {
    title: "Agent Behavior",
    body:
      "Upstream Hermes Agent behavior lives in `HermesConfigSection` with `activeView=\"agent\"`. In HAM, agent instruction budgets are edited via context / Memory Heist settings on the API host — not yet exposed in this workspace UI.",
  },
  routing: {
    title: "Smart Routing",
    body:
      "Upstream maps to `HermesConfigSection` (`activeView=\"routing\"`) and smart model routing. HAM uses server-side gateway and Memory Heist routing; this surface is a bridge until parity is wired.",
  },
  voice: {
    title: "Voice",
    body:
      "Upstream `HermesConfigSection` (`activeView=\"voice\"`) configures TTS/STT. HAM does not expose voice pipelines in the browser workspace shell yet.",
  },
  display: {
    title: "Display",
    body: "Use the Display section for the local desktop bundle panel.",
  },
  appearance: {
    title: "Appearance",
    body:
      "Upstream `WorkspaceThemePicker` and accent live here. HAM theme follows the main app; full workspace theme parity is limited in this bridge build.",
  },
  chat: {
    title: "Chat",
    body:
      "Upstream `ChatDisplaySection` controls tool messages, reasoning blocks, enter key, width, etc. Those map to chat store / main HAM chat, not yet split in this workspace-only screen.",
  },
  notifications: {
    title: "Notifications",
    body:
      "Upstream toggles alerts, usage threshold, and smart suggestions. HAM uses different server-side notifications; bridge only until mapped.",
  },
  mcp: {
    title: "MCP Servers",
    body: "Use the dedicated MCP route to match upstream file `src/routes/settings/mcp.tsx`.",
  },
  language: {
    title: "Language",
    body:
      "Upstream `LOCALE_LABELS` / `setLocale` UI. HAM dashboard language is not switched from this workspace settings page yet.",
  },
};

type WorkspaceSettingsBridgePanelProps = {
  section: UpstreamSettingsNavId;
};

export function WorkspaceSettingsBridgePanel({ section }: WorkspaceSettingsBridgePanelProps) {
  const text = COPY[section];

  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center p-6 text-center md:min-h-[16rem]">
      <div className="max-w-md space-y-4 rounded-2xl border border-white/[0.08] bg-black/35 p-8">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04]">
          <Construction className="h-6 w-6 text-white/35" strokeWidth={1.5} />
        </div>
        <div className="space-y-2">
          <h2 className="text-lg font-semibold tracking-tight text-white/90">{text.title}</h2>
          <p className="text-[13px] leading-relaxed text-white/45">{text.body}</p>
        </div>
        <p className="font-mono text-[10px] uppercase tracking-widest text-white/25">
          bridge · upstream section={section}
        </p>
      </div>
    </div>
  );
}
