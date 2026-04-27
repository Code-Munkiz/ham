/**
 * Upstream-matched empty state: `src/screens/chat/components/chat-empty-state.tsx` (repomix).
 * Copy, chip labels, and structure align with Hermes Workspace; HAM public asset for avatar frame.
 */

import * as React from "react";
import { motion } from "motion/react";
import { Brain, Code, Puzzle } from "lucide-react";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";

export type SuggestionChip = {
  label: string;
  prompt: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
};

/** Exact upstream `SUGGESTIONS` (repomix `chat-empty-state.tsx`). */
export const WORKSPACE_CHAT_SUGGESTIONS: SuggestionChip[] = [
  {
    label: "Analyze workspace",
    prompt:
      "Analyze this workspace structure and give me 3 engineering risks. Use tools and keep it concise.",
    icon: Code,
  },
  {
    label: "Save a preference",
    prompt:
      'Save this to memory exactly: "For demos, respond in 3 bullets max and put risk first." Then confirm saved.',
    icon: Brain,
  },
  {
    label: "Create a file",
    prompt: "Create demo-checklist.md with 5 launch checks for this app.",
    icon: Puzzle,
  },
];

type WorkspaceChatEmptyStateProps = {
  onSuggestionClick?: (prompt: string) => void;
};

export function WorkspaceChatEmptyState({ onSuggestionClick }: WorkspaceChatEmptyStateProps) {
  const avatarSrc = hamWorkspaceLogoUrl();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="hww-chat-empty flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center px-4 py-8"
    >
      <div className="flex max-w-xl flex-col items-center text-center">
        <div className="mb-6 flex justify-center">
          {/*
            Same asset + same presentation as the sidebar top brand (`WorkspaceShell`):
            no bordered “card” frame — that was making the mark read like a wrong thumbnail.
          */}
          <img
            src={avatarSrc}
            alt=""
            className="h-7 w-7 shrink-0 object-contain opacity-95"
            width={28}
            height={28}
          />
        </div>
        <p className="hww-chat-micro-label mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-white/50">
          HAM's Workspace
        </p>
        <h2 className="text-2xl font-semibold tracking-tight text-[#e8eef8] md:text-3xl">Begin a session</h2>
        <p className="mt-3 text-sm text-white/40">Agent chat · live tools · memory · full observability</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {WORKSPACE_CHAT_SUGGESTIONS.map((suggestion) => {
            const Icon = suggestion.icon;
            return (
              <button
                key={suggestion.label}
                type="button"
                onClick={() => onSuggestionClick?.(suggestion.prompt)}
                className="hww-chat-chip flex cursor-pointer items-center gap-2 rounded-md px-3.5 py-2 text-xs font-medium text-[#e2eaf3] transition-all"
              >
                <Icon className="h-3.5 w-3.5 text-[#c45c12]/90" strokeWidth={1.5} />
                {suggestion.label}
              </button>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}
