import * as React from "react";
import { motion } from "motion/react";
import { Briefcase, ClipboardList, Sparkles } from "lucide-react";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import {
  BUILDER_EXAMPLE_PROMPTS,
  BUILDER_FIRST_RUN_HEADLINE,
  BUILDER_FIRST_RUN_MICRO_LABEL,
  BUILDER_FIRST_RUN_PREVIEW_NOTE,
  BUILDER_FIRST_RUN_SUBHEADLINE,
} from "@/lib/ham/builderFirstRunOnboarding";

export type SuggestionChip = {
  label: string;
  prompt: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
};

/** Starter prompts above the composer — builder-first examples for Lane A beta. */
export const WORKSPACE_CHAT_SUGGESTIONS: SuggestionChip[] = [
  {
    label: "Newsletter landing page",
    prompt: BUILDER_EXAMPLE_PROMPTS[0].prompt,
    icon: Sparkles,
  },
  {
    label: "Simple task tracker",
    prompt: BUILDER_EXAMPLE_PROMPTS[1].prompt,
    icon: ClipboardList,
  },
  {
    label: "Portfolio with contact form",
    prompt: BUILDER_EXAMPLE_PROMPTS[2].prompt,
    icon: Briefcase,
  },
];

export type WorkspaceChatEmptyStateProps = {
  onExamplePromptSelect?: (prompt: string) => void;
};

export function WorkspaceChatEmptyState({ onExamplePromptSelect }: WorkspaceChatEmptyStateProps) {
  const avatarSrc = hamWorkspaceLogoUrl();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="hww-chat-empty flex min-h-0 min-w-0 max-w-full flex-1 flex-col items-center justify-center overflow-x-hidden px-4 py-8"
      data-testid="hww-chat-empty-state"
    >
      <div className="flex max-w-full min-w-0 flex-col items-center text-center">
        <motion.div className="mb-6 flex justify-center">
          <img
            src={avatarSrc}
            alt=""
            className="h-12 w-12 shrink-0 object-contain opacity-95"
            width={48}
            height={48}
          />
        </motion.div>
        <p className="hww-chat-micro-label mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-white/50">
          {BUILDER_FIRST_RUN_MICRO_LABEL}
        </p>
        <h2
          className="text-2xl font-semibold tracking-tight text-[#e8eef8] md:text-3xl"
          data-testid="hww-chat-empty-headline"
        >
          {BUILDER_FIRST_RUN_HEADLINE}
        </h2>
        <p
          className="mt-3 max-w-md text-sm leading-relaxed text-white/55"
          data-testid="hww-chat-empty-subheadline"
        >
          {BUILDER_FIRST_RUN_SUBHEADLINE}
        </p>
        <p className="mt-2 max-w-md text-[13px] leading-relaxed text-white/45">
          {BUILDER_FIRST_RUN_PREVIEW_NOTE}
        </p>
        {onExamplePromptSelect ? (
          <div
            className="mt-8 flex w-full max-w-lg flex-col items-stretch gap-2 sm:items-center"
            data-testid="hww-chat-empty-examples"
          >
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-white/40">
              Try an example
            </p>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
              {BUILDER_EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example.label}
                  type="button"
                  data-testid={`hww-chat-empty-example-${example.label.replace(/\s+/g, "-").toLowerCase()}`}
                  className="rounded-full border border-white/[0.1] bg-white/[0.04] px-3 py-2 text-left text-[12px] font-medium text-[#e4edf4] outline-none transition hover:border-emerald-500/35 hover:bg-white/[0.07] focus-visible:ring-2 focus-visible:ring-emerald-500/30"
                  onClick={() => onExamplePromptSelect(example.prompt)}
                >
                  {example.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}
