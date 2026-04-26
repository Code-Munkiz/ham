/**
 * Upstream-floating composer pattern (repomix `chat-composer` docked area) — HAM stream only, no send-stream.
 */

import * as React from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";

type WorkspaceChatComposerProps = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  sending: boolean;
  catalog: ModelCatalogPayload | null;
  modelId: string | null;
  onModelIdChange: (id: string | null) => void;
};

function chatModelCandidates(c: ModelCatalogPayload | null): ModelCatalogItem[] {
  if (!c?.items?.length) return [];
  return c.items.filter((x) => x.supports_chat);
}

export function WorkspaceChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  sending,
  catalog,
  modelId,
  onModelIdChange,
}: WorkspaceChatComposerProps) {
  const formRef = React.useRef<HTMLFormElement>(null);
  const showModel = catalog && catalog.gateway_mode === "openrouter" && chatModelCandidates(catalog).length > 0;
  const gatewayOk = isDashboardChatGatewayReady(catalog);

  return (
    <div
      className="hww-chat-composer-outer pointer-events-auto shrink-0 border-t border-white/[0.06] bg-[#030a10]/90 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-sm md:px-4"
    >
      {showModel ? (
        <div className="mb-2 flex w-full max-w-[56rem] flex-wrap items-center gap-2 md:pl-1">
          <label htmlFor="hww-chat-model" className="text-[10px] font-medium uppercase tracking-wide text-white/35">
            Model
          </label>
          <select
            id="hww-chat-model"
            className="hww-input max-w-md flex-1 rounded-md py-1.5 text-[12px]"
            value={modelId ?? ""}
            onChange={(e) => onModelIdChange(e.target.value ? e.target.value : null)}
            disabled={sending}
          >
            {chatModelCandidates(catalog!).map((m) => (
              <option key={m.id} value={m.id}>
                {m.label || m.id}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <form
        ref={formRef}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="w-full max-w-[56rem] md:pl-1"
      >
        <div
          className={cn(
            "flex items-end gap-2 rounded-2xl border border-white/[0.1] bg-[#050c14]/95 p-2 shadow-lg",
            "ring-0 focus-within:border-[#c45c12]/40 focus-within:shadow-[0_0_0_1px_rgba(196,92,18,0.2)]",
          )}
        >
          <label htmlFor="hww-chat-composer" className="sr-only">
            Message
          </label>
          <textarea
            id="hww-chat-composer"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit();
              }
            }}
            rows={1}
            disabled={disabled || sending}
            placeholder={
              !gatewayOk && catalog && !sending
                ? "Chat gateway not ready — check /api/models"
                : "Message Hermes…"
            }
            className="hww-input max-h-40 min-h-[44px] flex-1 resize-none border-0 bg-transparent px-2 py-2.5 text-[13px] text-[#e8eef3] placeholder:text-white/30 focus:ring-0"
          />
          <Button
            type="submit"
            size="icon"
            disabled={disabled || sending || !value.trim() || !gatewayOk}
            className="h-10 w-10 shrink-0 rounded-xl bg-gradient-to-b from-[#c45c12] to-[#8f3d0a] text-white hover:from-[#d66a18] hover:to-[#a44a0c] disabled:opacity-40"
            aria-label="Send"
          >
            {sending ? (
              <span className="h-4 w-4 animate-pulse rounded-full bg-white/80" />
            ) : (
              <ArrowUp className="h-4 w-4" strokeWidth={2.2} />
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
