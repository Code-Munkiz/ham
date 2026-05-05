import * as React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface CapField {
  field: string;
  label: string;
  min: number;
  max: number;
  value: number;
}

export interface CapsRowProps {
  idPrefix: string;
  fields: CapField[];
  onChange: (field: string, value: number) => void;
  disabled?: boolean;
}

export function CapsRow({
  idPrefix,
  fields,
  onChange,
  disabled,
}: CapsRowProps): React.ReactElement {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {fields.map((f) => {
        const id = `${idPrefix}__${f.field}`;
        return (
          <div key={f.field} className="flex flex-col gap-1.5">
            <Label htmlFor={id}>{f.label}</Label>
            <Input
              id={id}
              type="number"
              min={f.min}
              max={f.max}
              step={1}
              inputMode="numeric"
              value={Number.isFinite(f.value) ? f.value : 0}
              disabled={disabled}
              onChange={(e) => {
                const next = Number(e.target.value);
                onChange(f.field, Number.isFinite(next) ? next : 0);
              }}
            />
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              min {f.min} · max {f.max}
            </p>
          </div>
        );
      })}
    </div>
  );
}
