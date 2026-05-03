import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SAFETY_BOUNDS } from "../../lib/policyConstants";
import type { SafetyRules } from "../../lib/policyTypes";
import { TagInput } from "./TagInput";

export interface SafetyRulesFieldsProps {
  value: SafetyRules;
  onChange: (next: SafetyRules) => void;
  disabled?: boolean;
}

export function SafetyRulesFields({
  value,
  onChange,
  disabled,
}: SafetyRulesFieldsProps): React.ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Safety rules</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <TagInput
            id="safety__blocked_topics"
            label="Blocked topics"
            value={value.blocked_topics}
            onChange={(next) => onChange({ ...value, blocked_topics: next })}
            maxCount={SAFETY_BOUNDS.blocked_topics_max_count}
            disabled={disabled}
            placeholder="topic-slug"
            helpText="Slugs only. Up to 32 entries."
          />
        </div>
        <div className="flex items-center justify-between rounded-md border border-border/40 p-3">
          <div>
            <Label htmlFor="safety__block_links">Block links</Label>
            <p className="text-xs text-muted-foreground">
              Refuse outputs that contain URLs.
            </p>
          </div>
          <Switch
            id="safety__block_links"
            checked={value.block_links}
            disabled={disabled}
            onCheckedChange={(checked) =>
              onChange({ ...value, block_links: checked === true })
            }
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="safety__min_relevance">Minimum relevance</Label>
          <Input
            id="safety__min_relevance"
            type="number"
            min={SAFETY_BOUNDS.min_relevance.min}
            max={SAFETY_BOUNDS.min_relevance.max}
            step={SAFETY_BOUNDS.min_relevance.step}
            value={value.min_relevance}
            disabled={disabled}
            onChange={(e) => {
              const next = Number(e.target.value);
              onChange({
                ...value,
                min_relevance: Number.isFinite(next) ? next : 0,
              });
            }}
          />
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {SAFETY_BOUNDS.min_relevance.min} – {SAFETY_BOUNDS.min_relevance.max}
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="safety__consec_fail">Consecutive failure stop</Label>
          <Input
            id="safety__consec_fail"
            type="number"
            min={SAFETY_BOUNDS.consecutive_failure_stop.min}
            max={SAFETY_BOUNDS.consecutive_failure_stop.max}
            step={1}
            value={value.consecutive_failure_stop}
            disabled={disabled}
            onChange={(e) => {
              const next = Number(e.target.value);
              onChange({
                ...value,
                consecutive_failure_stop: Number.isFinite(next) ? next : 1,
              });
            }}
          />
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {SAFETY_BOUNDS.consecutive_failure_stop.min} – {SAFETY_BOUNDS.consecutive_failure_stop.max}
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="safety__policy_reject">Policy rejection stop</Label>
          <Input
            id="safety__policy_reject"
            type="number"
            min={SAFETY_BOUNDS.policy_rejection_stop.min}
            max={SAFETY_BOUNDS.policy_rejection_stop.max}
            step={1}
            value={value.policy_rejection_stop}
            disabled={disabled}
            onChange={(e) => {
              const next = Number(e.target.value);
              onChange({
                ...value,
                policy_rejection_stop: Number.isFinite(next) ? next : 1,
              });
            }}
          />
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {SAFETY_BOUNDS.policy_rejection_stop.min} – {SAFETY_BOUNDS.policy_rejection_stop.max}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
