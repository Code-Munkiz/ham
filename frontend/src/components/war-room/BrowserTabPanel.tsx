import { ExternalLink } from "lucide-react";

import { cn } from "@/lib/utils";

export interface BrowserTabPanelProps {
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
}

export function BrowserTabPanel({ embedUrl, onEmbedUrlChange }: BrowserTabPanelProps) {
  const src = embedUrl.trim().startsWith("https://") ? embedUrl.trim() : "";
  const canOpen = embedUrl.trim().startsWith("http");

  return (
    <div className="space-y-3 flex flex-col min-h-0 flex-1">
      <p className="text-[9px] font-bold text-white/35 uppercase tracking-widest">
        In-pane HTTPS preview — does not require an active Cloud Agent mission.
      </p>
      <input
        value={embedUrl}
        onChange={(e) => onEmbedUrlChange(e.target.value)}
        placeholder="https://…"
        className="w-full bg-black/50 border border-white/10 px-3 py-2 text-[10px] font-mono text-white/80 placeholder:text-white/20 outline-none focus:border-[#00E5FF]/40"
      />
      {src ? (
        <iframe
          title="In-pane browser preview"
          src={src}
          className="w-full flex-1 min-h-[220px] border border-[#00E5FF]/20 bg-black"
          sandbox="allow-scripts allow-same-origin allow-forms"
        />
      ) : (
        <div className="border border-dashed border-white/15 rounded p-6 text-[10px] text-white/30 text-center uppercase tracking-widest">
          Enter an HTTPS URL to embed
        </div>
      )}
      <a
        href={canOpen ? embedUrl.trim() : "#"}
        target="_blank"
        rel="noreferrer"
        className={cn(
          "inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest px-3 py-2 border border-white/15 w-fit",
          canOpen ? "text-[#00E5FF] hover:bg-white/5" : "text-white/20 pointer-events-none",
        )}
      >
        <ExternalLink className="h-3 w-3" />
        Open externally
      </a>
    </div>
  );
}
