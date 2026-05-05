import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { ADVISORY_LABELS } from "../lib/policyCopy";
import type { SocialPolicyAdvisoryCode } from "../lib/policyTypes";

export interface AdvisoryChipProps {
  code: string;
  className?: string;
}

/**
 * Read-only chip rendering a SocialPolicy advisory code with a friendly label.
 * Unknown codes still render with the raw code as a fallback so we never
 * silently swallow new server codes.
 */
export function AdvisoryChip({ code, className }: AdvisoryChipProps): React.ReactElement {
  const known = (ADVISORY_LABELS as Record<string, string | undefined>)[code];
  return (
    <Badge variant="warning" className={className} title={known ?? code}>
      {known ?? code}
    </Badge>
  );
}

export type { SocialPolicyAdvisoryCode };
