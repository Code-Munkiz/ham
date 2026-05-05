import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { SocialPolicyDoc } from "./lib/policyTypes";
import { PROVIDER_LABELS } from "./lib/policyCopy";
import { SUPPORTED_PROVIDER_IDS } from "./lib/policyConstants";

export interface PolicyReadViewProps {
  doc: SocialPolicyDoc | null;
}

export function PolicyReadView({ doc }: PolicyReadViewProps): React.ReactElement {
  if (!doc) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Policy</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No policy loaded.</p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Policy snapshot</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">autopilot: {doc.autopilot_mode}</Badge>
          <Badge variant={doc.live_autonomy_armed ? "warning" : "outline"}>
            live: {doc.live_autonomy_armed ? "armed" : "off"}
          </Badge>
          <Badge variant="secondary">
            persona: {doc.persona.persona_id} v{doc.persona.persona_version}
          </Badge>
        </div>
        <ul className="space-y-1 text-xs">
          {SUPPORTED_PROVIDER_IDS.map((id) => {
            const p = doc.providers[id];
            if (!p) return null;
            return (
              <li key={id}>
                <strong>{PROVIDER_LABELS[id]}</strong>: posting={p.posting_mode} · reply=
                {p.reply_mode} · actions=[{p.posting_actions_allowed.join(",") || "—"}]
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
