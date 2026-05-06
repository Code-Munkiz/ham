import * as React from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { SUPPORTED_TARGET_LABELS } from "../../lib/policyConstants";
import type { ChannelTarget, ChannelTargetLabel } from "../../lib/policyTypes";

export interface TargetsToggleRowProps {
  idPrefix: string;
  value: ChannelTarget[];
  onChange: (next: ChannelTarget[]) => void;
  disabled?: boolean;
}

const LABEL_DESCRIPTIONS: Record<ChannelTargetLabel, string> = {
  home_channel: "Home channel — primary delivery target.",
  test_group: "Test group — sandbox delivery target for previews.",
};

export function TargetsToggleRow({
  idPrefix,
  value,
  onChange,
  disabled,
}: TargetsToggleRowProps): React.ReactElement {
  function isEnabled(label: ChannelTargetLabel): boolean {
    return value.find((t) => t.label === label)?.enabled === true;
  }
  function toggle(label: ChannelTargetLabel, enabled: boolean): void {
    const next: ChannelTarget[] = SUPPORTED_TARGET_LABELS.map((lbl) => {
      const found = value.find((t) => t.label === lbl);
      const target: ChannelTarget = {
        label: lbl,
        enabled: lbl === label ? enabled : found?.enabled === true,
      };
      return target;
    }).filter((t) => t.enabled || value.find((v) => v.label === t.label));
    onChange(next);
  }
  return (
    <div className="flex flex-col gap-3">
      {SUPPORTED_TARGET_LABELS.map((lbl) => {
        const id = `${idPrefix}__target_${lbl}`;
        return (
          <div
            key={lbl}
            className="flex items-start justify-between gap-3 rounded-md border border-border/40 p-3"
          >
            <div className="flex-1">
              <Label htmlFor={id} className="text-sm">
                {lbl}
              </Label>
              <p className="text-xs text-muted-foreground">{LABEL_DESCRIPTIONS[lbl]}</p>
            </div>
            <Switch
              id={id}
              checked={isEnabled(lbl)}
              disabled={disabled}
              onCheckedChange={(checked) => toggle(lbl, checked === true)}
            />
          </div>
        );
      })}
    </div>
  );
}
