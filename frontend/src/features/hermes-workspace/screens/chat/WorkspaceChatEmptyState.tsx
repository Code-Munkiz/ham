/**
 * Upstream-matched empty state: `src/screens/chat/components/chat-empty-state.tsx` (repomix).
 * Copy, chip labels, and structure align with Hermes Workspace; HAM public asset for avatar frame.
 */

import * as React from "react";
import { motion } from "motion/react";
import { Brain, Code, Puzzle } from "lucide-react";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import { CodingPlanPanel } from "./coding-plan/CodingPlanPanel";

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

export function WorkspaceChatEmptyState() {
  const avatarSrc = hamWorkspaceLogoUrl();
  const [showCodingPlan, setShowCodingPlan] = React.useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="hww-chat-empty flex min-h-0 min-w-0 max-w-full flex-1 flex-col items-center justify-center overflow-x-hidden px-4 py-8"
    >
      <div className="flex max-w-full min-w-0 flex-col items-center text-center">
        <div className="mb-6 flex justify-center">
          {/*
            Same asset + same presentation as the sidebar top brand (`WorkspaceShell`):
            no bordered “card” frame — that was making the mark read like a wrong thumbnail.
          */}
          <img
            src={avatarSrc}
            alt=""
            className="h-12 w-12 shrink-0 object-contain opacity-95"
            width={48}
            height={48}
          />
        </div>
        <p className="hww-chat-micro-label mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-white/50">
          HAM's Workspace
        </p>
        <h2 className="text-2xl font-semibold tracking-tight text-[#e8eef8] md:text-3xl">
          Begin a session
        </h2>
        <p className="mt-3 text-sm text-white/40">
          Agent chat · live tools · memory · full observability
        </p>
        <p className="mt-8 max-w-sm text-[12px] leading-relaxed text-white/40">
          Use the scrolling starter prompts above the composer to jump in—they send the same quick
          actions as before.
        </p>
        <div className="mt-6 w-full max-w-md">
          {showCodingPlan ? (
            <CodingPlanPanel onClose={() => setShowCodingPlan(false)} />
          ) : (
            <button
              type="button"
              onClick={() => setShowCodingPlan(true)}
              className="text-[11px] font-medium text-cyan-300/85 hover:text-cyan-200"
              data-hww-coding-plan-open
            >
              Plan with coding agents
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}
