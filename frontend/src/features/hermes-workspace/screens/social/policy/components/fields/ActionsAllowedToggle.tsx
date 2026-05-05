import * as React from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { POSTING_ACTION_LABELS } from "../../lib/policyCopy";
import { SUPPORTED_POSTING_ACTIONS } from "../../lib/policyConstants";
import type { PostingActionId } from "../../lib/policyTypes";

export interface ActionsAllowedToggleProps {
  idPrefix: string;
  value: PostingActionId[];
  onChange: (next: PostingActionId[]) => void;
  disabled?: boolean;
}

export function ActionsAllowedToggle({
  idPrefix,
  value,
  onChange,
  disabled,
}: ActionsAllowedToggleProps): React.ReactElement {
  function isOn(act: PostingActionId): boolean {
    return value.includes(act);
  }
  function toggle(act: PostingActionId, on: boolean): void {
    const set = new Set<PostingActionId>(value);
    if (on) set.add(act);
    else set.delete(act);
    // Preserve canonical order.
    const ordered = SUPPORTED_POSTING_ACTIONS.filter((a) => set.has(a));
    onChange(ordered);
  }
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
      {SUPPORTED_POSTING_ACTIONS.map((act) => {
        const id = `${idPrefix}__action_${act}`;
        return (
          <div key={act} className="flex items-center justify-between rounded-md border border-border/40 p-3">
            <Label htmlFor={id} className="text-sm capitalize">
              {POSTING_ACTION_LABELS[act]}
            </Label>
            <Switch
              id={id}
              checked={isOn(act)}
              disabled={disabled}
              onCheckedChange={(checked) => toggle(act, checked === true)}
            />
          </div>
        );
      })}
    </div>
  );
}
