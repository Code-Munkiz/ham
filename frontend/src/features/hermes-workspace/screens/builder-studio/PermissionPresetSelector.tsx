import * as React from "react";
import { PERMISSION_PRESET_LABELS, type PermissionPreset } from "./builderStudioLabels";
import { permissionPresetPreview } from "./permissionPresetPreview";

const ORDERED_PRESETS: PermissionPreset[] = [
  "safe_docs",
  "app_build",
  "bug_fix",
  "refactor",
  "game_build",
  "test_write",
  "readonly_analyst",
];

export function PermissionPresetSelector({
  value,
  onChange,
  showAdvanced,
  allowCustom = false,
}: {
  value: PermissionPreset;
  onChange: (next: PermissionPreset) => void;
  showAdvanced: boolean;
  /** Custom preset requires path/operation rules; keep false in Create Wizard until those fields exist. */
  allowCustom?: boolean;
}) {
  const presets: PermissionPreset[] = [
    ...ORDERED_PRESETS,
    ...(showAdvanced && allowCustom ? (["custom"] as const) : []),
  ];

  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-white/75">Safety level</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {presets.map((preset) => {
          const selected = value === preset;
          return (
            <label
              key={preset}
              className={
                "flex cursor-pointer flex-col gap-1 rounded-xl border px-3 py-2 transition-colors " +
                (selected
                  ? "border-emerald-300/40 bg-emerald-950/35"
                  : "border-white/15 bg-[#141c26] hover:border-white/25")
              }
            >
              <div className="flex items-center gap-2">
                <input
                  type="radio"
                  name="permission_preset"
                  value={preset}
                  checked={selected}
                  onChange={() => onChange(preset)}
                  className="h-3.5 w-3.5 accent-[var(--theme-accent)]"
                />
                <span className="text-sm font-medium text-white/95">
                  {PERMISSION_PRESET_LABELS[preset]}
                </span>
              </div>
              <span className="text-[11px] leading-snug text-white/65">
                {permissionPresetPreview(preset)}
              </span>
              {preset === "custom" ? (
                <span className="text-[10px] text-amber-200/80">
                  Advanced — paths only. You can&apos;t relax HAM&apos;s safety rules.
                </span>
              ) : null}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
