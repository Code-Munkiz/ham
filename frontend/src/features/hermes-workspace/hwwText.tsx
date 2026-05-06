import * as React from "react";

/**
 * HAM-only: small safe subset of Markdown for mission/agent output (no HTML, no network).
 * Renders as React text nodes; supports **bold**, `code`, # / ## / ###, bullets.
 */
function renderInline(s: string, key: string): React.ReactNode {
  if (!s) return null;
  const p: React.ReactNode[] = [];
  let i = 0;
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let m: RegExpExecArray | null;
  let last = 0;
  while ((m = re.exec(s)) !== null) {
    if (m.index > last) p.push(<span key={`${key}-t-${i++}`}>{s.slice(last, m.index)}</span>);
    const tok = m[1]!;
    if (tok.startsWith("**")) {
      p.push(
        <strong key={`${key}-b-${i++}`} className="font-semibold text-amber-100/95">
          {tok.slice(2, -2)}
        </strong>,
      );
    } else {
      p.push(
        <code
          key={`${key}-c-${i++}`}
          className="rounded border border-white/10 bg-black/50 px-1 py-0.5 font-mono text-[0.9em] text-cyan-100/90"
        >
          {tok.slice(1, -1)}
        </code>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < s.length) p.push(<span key={`${key}-t-${i++}`}>{s.slice(last)}</span>);
  return p.length ? p : s;
}

function renderBlock(text: string, bIdx: number) {
  const t = text.replace(/\n+$/, "");
  const lines = t.split("\n");
  const out: React.ReactNode[] = [];
  lines.forEach((line, li) => {
    const m = /^(#{1,3})\s+(.+)$/.exec(line);
    if (m) {
      const level = m[1]!.length;
      const H = (level === 1 ? "h3" : level === 2 ? "h4" : "h5") as "h3" | "h4" | "h5";
      const body = m[2]!;
      out.push(
        <H
          key={`b${bIdx}h${li}`}
          className={
            level === 1
              ? "mt-1 text-sm font-semibold text-white/95"
              : level === 2
                ? "mt-1 text-xs font-semibold text-white/90"
                : "mt-0.5 text-[11px] font-medium text-white/80"
          }
        >
          {renderInline(body, `b${bIdx}h${li}i`)}
        </H>,
      );
      return;
    }
    if (/^[-*]\s+/.test(line)) {
      out.push(
        <div key={`b${bIdx}u${li}`} className="ml-1 flex gap-1.5 text-[11px] text-white/75">
          <span className="text-amber-400/80">•</span>
          <span className="min-w-0 flex-1">
            {renderInline(line.replace(/^[-*]\s+/, ""), `b${bIdx}l${li}`)}
          </span>
        </div>,
      );
      return;
    }
    if (line.trim() === "") {
      out.push(<br key={`b${bIdx}e${li}`} />);
      return;
    }
    out.push(
      <p
        key={`b${bIdx}p${li}`}
        className="whitespace-pre-wrap text-[11px] leading-relaxed text-white/80"
      >
        {renderInline(line, `b${bIdx}p${li}i`)}
      </p>,
    );
  });
  return <div className="space-y-0.5">{out}</div>;
}

type HwwTextProps = {
  text: string;
  className?: string;
};

export function HwwText({ text, className }: HwwTextProps) {
  if (!text.trim()) return <span className="text-white/30">—</span>;
  const blocks = text.split(/\n{2,}/);
  return (
    <div className={className ?? "hww-prose min-w-0"}>
      {blocks.map((b, i) => (
        <div key={i} className={i > 0 ? "mt-2" : ""}>
          {renderBlock(b, i)}
        </div>
      ))}
    </div>
  );
}

export function hwwCentsToUsd(cents: number) {
  const c = Math.max(0, Math.round(cents));
  return (c / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

/** Heuristic: map cents → displayed token count (cosmetic; not gateway-computed). */
export function hwwCentsToEstTokens(cents: number) {
  return Math.max(0, Math.round(cents * 4));
}
