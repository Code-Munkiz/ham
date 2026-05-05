import * as React from "react";
import { Label } from "@/components/ui/label";

export interface ModeSelectOption {
  value: string;
  label: string;
}

export interface ModeSelectProps {
  id: string;
  label: string;
  value: string;
  options: readonly ModeSelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  helpText?: string;
}

export function ModeSelect({
  id,
  label,
  value,
  options,
  onChange,
  disabled,
  helpText,
}: ModeSelectProps): React.ReactElement {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {helpText ? <p className="text-xs text-muted-foreground">{helpText}</p> : null}
    </div>
  );
}
