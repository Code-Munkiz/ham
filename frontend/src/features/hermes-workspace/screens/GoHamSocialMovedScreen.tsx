import * as React from "react";
import { ExternalLink } from "lucide-react";

const LUV_SOCIAL_REPO = "https://github.com/luv-protocol/luv-social";

/** Minimal landing when legacy /workspace/social bookmarks hit HAM after Mission 20 extraction. */
export function GoHamSocialMovedScreen() {
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 p-6 text-white/90">
      <h1 className="text-xl font-semibold text-white">GoHAM Social has moved</h1>
      <p className="text-sm leading-relaxed text-white/70">
        Autonomous social-agent operations (Telegram, schedulers, caps, and social safety) now live in
        a standalone Luv Protocol project. HAM remains the builder, workspace, and coding-agent
        platform.
      </p>
      <a
        href={LUV_SOCIAL_REPO}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex w-fit items-center gap-2 rounded-md border border-white/15 bg-white/5 px-4 py-2 text-sm font-medium text-[#ffb27a] hover:bg-white/10"
      >
        luv-protocol/luv-social
        <ExternalLink className="h-4 w-4" aria-hidden />
      </a>
    </div>
  );
}
