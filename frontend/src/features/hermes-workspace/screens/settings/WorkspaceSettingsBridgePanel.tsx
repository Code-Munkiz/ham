import * as React from "react";
import { Construction } from "lucide-react";

const COPY: Record<string, { title: string; body: string }> = {
  language: {
    title: "Language",
    body: "Upstream locale and copy preferences are not wired in this HAM build. Your system browser language still applies.",
  },
  appearance: {
    title: "Appearance",
    body: "Theme and density are controlled from the main HAM app and this shell; a full upstream theme switcher will land with the next bridge pass.",
  },
  chat: {
    title: "Chat",
    body: "Composer and inline behavior use the main HAM chat stack. Advanced upstream chat toggles are not exposed here yet.",
  },
  notifications: {
    title: "Notifications",
    body: "Push and desktop notifications are not connected in the browser workspace shell for this preview.",
  },
  voice: {
    title: "Voice",
    body: "Voice input and read-back are not enabled in the local HAM workspace bridge.",
  },
  hermes: {
    title: "Hermes",
    body: "Hermes-specific upstream options are represented in HAM via API keys, context, and desktop bundle; there is no separate remote Hermes host in the browser.",
  },
  providers: {
    title: "Providers",
    body: "Provider routing is configured through API keys, environment, and model settings. A dedicated provider matrix will map here when the adapter is ready.",
  },
};

type WorkspaceSettingsBridgePanelProps = {
  bridgeKey: string;
};

export function WorkspaceSettingsBridgePanel({ bridgeKey }: WorkspaceSettingsBridgePanelProps) {
  const text = COPY[bridgeKey] ?? {
    title: "Not available",
    body: "This section is reserved for upstream parity. HAM does not expose this control in the workspace bridge yet.",
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col items-center justify-center p-8 text-center">
      <div className="max-w-md space-y-4 rounded-2xl border border-white/[0.08] bg-black/35 p-8">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04]">
          <Construction className="h-6 w-6 text-white/35" strokeWidth={1.5} />
        </div>
        <div className="space-y-2">
          <h2 className="text-lg font-semibold tracking-tight text-white/90">{text.title}</h2>
          <p className="text-[13px] leading-relaxed text-white/45">{text.body}</p>
        </div>
        <p className="font-mono text-[10px] uppercase tracking-widest text-white/25">bridge · {bridgeKey}</p>
      </div>
    </div>
  );
}
