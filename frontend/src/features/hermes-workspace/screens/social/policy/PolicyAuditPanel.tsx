import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UI_TEXT } from "./lib/policyCopy";
import type { SocialPolicyAuditEnvelope } from "./lib/policyTypes";

export interface PolicyAuditPanelProps {
  audits: SocialPolicyAuditEnvelope[];
  loading?: boolean;
  errorMessage?: string | null;
}

function shortRev(rev: string | undefined): string {
  if (!rev) return "—";
  return rev.length > 16 ? `${rev.slice(0, 12)}…` : rev;
}

export function PolicyAuditPanel({
  audits,
  loading,
  errorMessage,
}: PolicyAuditPanelProps): React.ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">{UI_TEXT.loading}</p>
        ) : errorMessage ? (
          <p className="text-sm text-destructive">{errorMessage}</p>
        ) : audits.length === 0 ? (
          <p className="text-sm text-muted-foreground">{UI_TEXT.auditEmpty}</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border/40">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide">
                <tr>
                  <th className="p-2 text-left">Audit id</th>
                  <th className="p-2 text-left">Timestamp</th>
                  <th className="p-2 text-left">Action</th>
                  <th className="p-2 text-left">Previous → new</th>
                  <th className="p-2 text-left">Live</th>
                </tr>
              </thead>
              <tbody>
                {audits.map((a, idx) => (
                  <tr key={a.audit_id ?? `audit_${idx}`} className="border-t border-border/40">
                    <td className="p-2 font-mono text-xs">{a.audit_id ?? "—"}</td>
                    <td className="p-2 text-xs">{a.timestamp ?? "—"}</td>
                    <td className="p-2 text-xs">{a.action ?? "—"}</td>
                    <td className="p-2 font-mono text-xs">
                      {shortRev(a.previous_revision)} → {shortRev(a.new_revision)}
                    </td>
                    <td className="p-2 text-xs">
                      {a.live_autonomy_change ? (
                        <Badge variant="warning">change</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
