import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { UI_TEXT } from "./lib/policyCopy";
import type { SocialPolicyPreviewResponse } from "./lib/policyTypes";

export interface PolicyDiffViewProps {
  preview: SocialPolicyPreviewResponse;
  applyDisabled: boolean;
  applyDisabledReason?: string;
  onApply: () => void;
  onCancel: () => void;
}

function fmt(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "—";
  if (typeof value === "string") return JSON.stringify(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function PolicyDiffView({
  preview,
  applyDisabled,
  applyDisabledReason,
  onApply,
  onCancel,
}: PolicyDiffViewProps): React.ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Preview</span>
          <Badge variant="outline">base {preview.base_revision.slice(0, 12)}…</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {preview.warnings.length > 0 ? (
          <ul className="space-y-1 text-xs">
            {preview.warnings.map((w) => (
              <li key={w}>
                <Badge variant="warning">{w}</Badge>
              </li>
            ))}
          </ul>
        ) : null}

        {preview.live_autonomy_change ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            Live autonomy change detected in the diff. The editor cannot save this — reset and
            re-edit.
          </div>
        ) : null}

        {preview.diff.length === 0 ? (
          <p className="text-sm text-muted-foreground">No effective changes.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border/40">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide">
                <tr>
                  <th className="p-2 text-left">Path</th>
                  <th className="p-2 text-left">Before</th>
                  <th className="p-2 text-left">After</th>
                </tr>
              </thead>
              <tbody>
                {preview.diff.map((d) => (
                  <tr key={d.path} className="border-t border-border/40 align-top">
                    <td className="p-2 font-mono text-xs">{d.path}</td>
                    <td className="p-2 font-mono text-xs text-muted-foreground">{fmt(d.before)}</td>
                    <td className="p-2 font-mono text-xs">{fmt(d.after)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          {applyDisabled && applyDisabledReason ? (
            <span className="text-xs text-muted-foreground">{applyDisabledReason}</span>
          ) : null}
          <Button variant="outline" onClick={onCancel}>
            {UI_TEXT.cancelButton}
          </Button>
          <Button disabled={applyDisabled} onClick={onApply}>
            {UI_TEXT.applyButton}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
