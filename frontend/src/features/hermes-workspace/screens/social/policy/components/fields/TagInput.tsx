import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TAG_SLUG_RE, TOKEN_SHAPE_RE, RAW_NUMERIC_ID_RE } from "../../lib/policyConstants";

export interface TagInputProps {
  id: string;
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  maxCount: number;
  disabled?: boolean;
  placeholder?: string;
  helpText?: string;
}

function normalize(raw: string): { ok: true; value: string } | { ok: false; reason: string } {
  const text = raw.trim();
  if (!text) return { ok: false, reason: "empty" };
  if (text.length > 64) return { ok: false, reason: "must be ≤64 chars" };
  if (!TAG_SLUG_RE.test(text)) return { ok: false, reason: "must be a lower-case slug" };
  if (TOKEN_SHAPE_RE.test(text)) return { ok: false, reason: "looks like a token" };
  if (RAW_NUMERIC_ID_RE.test(text)) return { ok: false, reason: "looks like a raw ID" };
  return { ok: true, value: text };
}

export function TagInput({
  id,
  label,
  value,
  onChange,
  maxCount,
  disabled,
  placeholder,
  helpText,
}: TagInputProps): React.ReactElement {
  const [input, setInput] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);

  function add(): void {
    if (value.length >= maxCount) {
      setErr(`at most ${maxCount} entries`);
      return;
    }
    const result = normalize(input);
    if (result.ok === false) {
      setErr(result.reason);
      return;
    }
    if (value.includes(result.value)) {
      setErr("duplicate");
      return;
    }
    onChange([...value, result.value]);
    setInput("");
    setErr(null);
  }
  function remove(idx: number): void {
    const next = [...value];
    next.splice(idx, 1);
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex flex-wrap gap-1.5">
        {value.map((t, idx) => (
          <Badge key={`${t}-${idx}`} variant="outline" className="gap-1">
            <span>{t}</span>
            <button
              type="button"
              aria-label={`Remove ${t}`}
              className="ml-1 text-muted-foreground hover:text-foreground"
              disabled={disabled}
              onClick={() => remove(idx)}
            >
              ×
            </button>
          </Badge>
        ))}
        {value.length === 0 ? (
          <span className="text-xs text-muted-foreground">none</span>
        ) : null}
      </div>
      <div className="flex gap-2">
        <Input
          id={id}
          value={input}
          disabled={disabled}
          placeholder={placeholder ?? "lower-case-slug"}
          onChange={(e) => {
            setInput(e.target.value);
            setErr(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" variant="secondary" disabled={disabled} onClick={add}>
          Add
        </Button>
      </div>
      {err ? (
        <p className="text-xs text-destructive">{err}</p>
      ) : helpText ? (
        <p className="text-xs text-muted-foreground">{helpText}</p>
      ) : null}
    </div>
  );
}
