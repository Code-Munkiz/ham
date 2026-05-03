import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UI_TEXT } from "./lib/policyCopy";
import type { SocialPolicyBackupListItem } from "./lib/policyTypes";

export interface PolicyHistoryPanelProps {
  backups: SocialPolicyBackupListItem[];
  loading?: boolean;
  errorMessage?: string | null;
}

export function PolicyHistoryPanel({
  backups,
  loading,
  errorMessage,
}: PolicyHistoryPanelProps): React.ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">{UI_TEXT.loading}</p>
        ) : errorMessage ? (
          <p className="text-sm text-destructive">{errorMessage}</p>
        ) : backups.length === 0 ? (
          <p className="text-sm text-muted-foreground">{UI_TEXT.historyEmpty}</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border/40">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide">
                <tr>
                  <th className="p-2 text-left">Backup id</th>
                  <th className="p-2 text-left">Timestamp</th>
                  <th className="p-2 text-right">Size (B)</th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.backup_id} className="border-t border-border/40">
                    <td className="p-2 font-mono text-xs">{b.backup_id}</td>
                    <td className="p-2 text-xs">{b.timestamp_iso}</td>
                    <td className="p-2 text-right text-xs">{b.size_bytes}</td>
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
