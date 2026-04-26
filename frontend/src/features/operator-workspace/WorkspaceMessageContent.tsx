import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Hermes-style message body: paragraphs, **bold**, `code`, `###` headings, `-` lists.
 * Renders as React nodes (no raw HTML) — content is user/assistant text from HAM, not untrusted web.
 */
function parseInlines(text: string): React.ReactNode[] {
  if (!text) return [];
  const segments = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return segments.map((seg, i) => {
    if (seg.startsWith("**") && seg.endsWith("**") && seg.length >= 4) {
      return (
        <strong key={i} className="font-semibold text-white/95">
          {seg.slice(2, -2)}
        </strong>
      );
    }
    if (seg.startsWith("`") && seg.endsWith("`") && seg.length >= 2) {
      return (
        <code
          key={i}
          className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em] text-amber-100/90"
        >
          {seg.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{seg}</span>;
  });
}

type WorkspaceMessageContentProps = {
  content: string;
  className?: string;
};

export function WorkspaceMessageContent({
  content,
  className,
}: WorkspaceMessageContentProps) {
  const blocks = content.split(/\n{2,}/);

  return (
    <div
      className={cn(
        "ow-msg-content text-[0.8125rem] leading-relaxed text-white/[0.92] [text-wrap:pretty]",
        className,
      )}
    >
      {blocks.map((block, blockIdx) => {
        const lines = block.split("\n");
        const first = lines[0] ?? "";
        const rest = lines.slice(1);

        if (first.startsWith("### ")) {
          return (
            <h4
              key={blockIdx}
              className="mb-1.5 mt-2 first:mt-0 text-[0.7rem] font-semibold uppercase tracking-[0.08em] text-white/55"
            >
              {parseInlines(first.slice(4))}
              {rest.length
                ? rest.map((line, j) => (
                    <span key={j}>
                      <br />
                      {parseInlines(line)}
                    </span>
                  ))
                : null}
            </h4>
          );
        }

        const nonEmpty = lines.filter((l) => l.trim() !== "");
        const allBullets =
          nonEmpty.length > 0 && nonEmpty.every((l) => l.trim().startsWith("- "));

        if (allBullets) {
          return (
            <ul
              key={blockIdx}
              className="mb-2 list-none space-y-1 pl-0 last:mb-0 marker:text-white/30"
            >
              {nonEmpty.map((line, j) => (
                <li key={j} className="flex gap-2 pl-0 text-white/88">
                  <span className="mt-0.5 shrink-0 text-white/35" aria-hidden>
                    ·
                  </span>
                  <span>{parseInlines(line.replace(/^\s*-\s+/, ""))}</span>
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p key={blockIdx} className="mb-2 last:mb-0 text-white/88">
            {lines.map((line, li) => (
              <React.Fragment key={li}>
                {li > 0 ? <br /> : null}
                {parseInlines(line)}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
