import * as React from "react";
import { AdvisoryChip } from "./AdvisoryChip";

export interface AdvisoryChipsRowProps {
  reasons: readonly string[] | undefined | null;
  label?: string;
  className?: string;
}

/**
 * Renders a horizontal row of advisory chips (D.2 codes from
 * `policy_advisory_reasons`). Renders nothing if there are no reasons.
 */
export function AdvisoryChipsRow({
  reasons,
  label,
  className,
}: AdvisoryChipsRowProps): React.ReactElement | null {
  if (!reasons || reasons.length === 0) return null;
  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className ?? ""}`.trim()}>
      {label ? <span className="text-xs font-medium text-muted-foreground">{label}</span> : null}
      {reasons.map((code) => (
        <AdvisoryChip key={code} code={code} />
      ))}
    </div>
  );
}
