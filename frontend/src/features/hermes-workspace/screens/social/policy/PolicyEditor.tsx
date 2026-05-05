import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AUTOPILOT_MODE_VALUES,
  POSTING_CAP_BOUNDS,
  POSTING_CAP_FIELDS,
  PROVIDER_MODE_VALUES,
  REPLY_CAP_BOUNDS,
  REPLY_CAP_FIELDS,
  SUPPORTED_PROVIDER_IDS,
} from "./lib/policyConstants";
import { AUTOPILOT_MODE_LABELS, PROVIDER_LABELS, PROVIDER_MODE_LABELS, UI_TEXT } from "./lib/policyCopy";
import { diffPolicy, hasPolicyChanges } from "./lib/policyDiff";
import { validatePolicy } from "./lib/policyValidate";
import type {
  AutopilotMode,
  ProviderId,
  ProviderMode,
  ProviderPolicy,
  SocialPolicyDoc,
} from "./lib/policyTypes";
import { ActionsAllowedToggle } from "./components/fields/ActionsAllowedToggle";
import { CapsRow } from "./components/fields/CapsRow";
import { ContentStyleFields } from "./components/fields/ContentStyleFields";
import { ModeSelect } from "./components/fields/ModeSelect";
import { SafetyRulesFields } from "./components/fields/SafetyRulesFields";
import { TargetsToggleRow } from "./components/fields/TargetsToggleRow";

export interface PolicyEditorProps {
  loadedDoc: SocialPolicyDoc;
  editedDoc: SocialPolicyDoc;
  onChange: (next: SocialPolicyDoc) => void;
  onPreview: () => void;
  onReset: () => void;
  disabled?: boolean;
  writesEnabled: boolean;
}

export function PolicyEditor({
  loadedDoc,
  editedDoc,
  onChange,
  onPreview,
  onReset,
  disabled,
  writesEnabled,
}: PolicyEditorProps): React.ReactElement {
  const validation = React.useMemo(() => validatePolicy(editedDoc), [editedDoc]);
  const localDiff = React.useMemo(
    () => diffPolicy(loadedDoc, editedDoc),
    [loadedDoc, editedDoc],
  );
  const dirty = hasPolicyChanges(loadedDoc, editedDoc);
  const canPreview = !disabled && validation.ok && dirty;

  function setProvider(id: ProviderId, next: ProviderPolicy): void {
    onChange({
      ...editedDoc,
      providers: { ...editedDoc.providers, [id]: next },
    });
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Global card */}
      <Card>
        <CardHeader>
          <CardTitle>Global</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <ModeSelect
            id="global__autopilot_mode"
            label="Autopilot mode"
            value={editedDoc.autopilot_mode}
            options={AUTOPILOT_MODE_VALUES.map((v) => ({
              value: v,
              label: AUTOPILOT_MODE_LABELS[v as AutopilotMode],
            }))}
            disabled={disabled}
            onChange={(v) => onChange({ ...editedDoc, autopilot_mode: v as AutopilotMode })}
          />
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium leading-none">Live autonomy armed</span>
            <div className="flex items-center gap-2">
              <Badge variant={editedDoc.live_autonomy_armed ? "warning" : "outline"}>
                {editedDoc.live_autonomy_armed ? "armed" : "off"}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {editedDoc.live_autonomy_armed
                  ? UI_TEXT.liveAutonomyReadOnly
                  : UI_TEXT.liveAutonomyReadOnlyOff}
              </span>
            </div>
          </div>
          <div className="md:col-span-2 flex flex-col gap-1.5">
            <span className="text-sm font-medium leading-none">Persona</span>
            <div className="flex items-center gap-2">
              <Badge variant="secondary">
                {editedDoc.persona.persona_id} v{editedDoc.persona.persona_version}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {UI_TEXT.personaReadOnly}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Per-provider cards */}
      {SUPPORTED_PROVIDER_IDS.map((id) => {
        const prov = editedDoc.providers[id];
        if (!prov) return null;
        return (
          <Card key={id}>
            <CardHeader>
              <CardTitle>{PROVIDER_LABELS[id]}</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <ModeSelect
                id={`provider_${id}__posting_mode`}
                label="Posting mode"
                value={prov.posting_mode}
                options={PROVIDER_MODE_VALUES.map((v) => ({
                  value: v,
                  label: PROVIDER_MODE_LABELS[v as ProviderMode],
                }))}
                disabled={disabled}
                onChange={(v) => setProvider(id, { ...prov, posting_mode: v as ProviderMode })}
              />
              <ModeSelect
                id={`provider_${id}__reply_mode`}
                label="Reply mode"
                value={prov.reply_mode}
                options={PROVIDER_MODE_VALUES.map((v) => ({
                  value: v,
                  label: PROVIDER_MODE_LABELS[v as ProviderMode],
                }))}
                disabled={disabled}
                onChange={(v) => setProvider(id, { ...prov, reply_mode: v as ProviderMode })}
              />
              <div className="md:col-span-2">
                <p className="mb-1.5 text-sm font-medium leading-none">Posting actions allowed</p>
                <ActionsAllowedToggle
                  idPrefix={`provider_${id}`}
                  value={prov.posting_actions_allowed}
                  onChange={(next) => setProvider(id, { ...prov, posting_actions_allowed: next })}
                  disabled={disabled}
                />
              </div>
              <div className="md:col-span-2">
                <p className="mb-1.5 text-sm font-medium leading-none">Posting caps</p>
                <CapsRow
                  idPrefix={`provider_${id}__posting_caps`}
                  disabled={disabled}
                  fields={[
                    {
                      field: POSTING_CAP_FIELDS.maxPerDay,
                      label: "Max per day",
                      ...POSTING_CAP_BOUNDS.max_per_day,
                      value: prov.posting_caps.max_per_day,
                    },
                    {
                      field: POSTING_CAP_FIELDS.maxPerRun,
                      label: "Max per run",
                      ...POSTING_CAP_BOUNDS.max_per_run,
                      value: prov.posting_caps.max_per_run,
                    },
                    {
                      field: POSTING_CAP_FIELDS.minSpacingMinutes,
                      label: "Min spacing (min)",
                      ...POSTING_CAP_BOUNDS.min_spacing_minutes,
                      value: prov.posting_caps.min_spacing_minutes,
                    },
                  ]}
                  onChange={(field, value) =>
                    setProvider(id, {
                      ...prov,
                      posting_caps: { ...prov.posting_caps, [field]: value },
                    })
                  }
                />
              </div>
              <div className="md:col-span-2">
                <p className="mb-1.5 text-sm font-medium leading-none">Reply caps</p>
                <CapsRow
                  idPrefix={`provider_${id}__reply_caps`}
                  disabled={disabled}
                  fields={[
                    {
                      field: REPLY_CAP_FIELDS.maxPer15m,
                      label: "Max per 15m",
                      ...REPLY_CAP_BOUNDS.max_per_15m,
                      value: prov.reply_caps.max_per_15m,
                    },
                    {
                      field: REPLY_CAP_FIELDS.maxPerHour,
                      label: "Max per hour",
                      ...REPLY_CAP_BOUNDS.max_per_hour,
                      value: prov.reply_caps.max_per_hour,
                    },
                    {
                      field: REPLY_CAP_FIELDS.maxPerUserPerDay,
                      label: "Max per user / day",
                      ...REPLY_CAP_BOUNDS.max_per_user_per_day,
                      value: prov.reply_caps.max_per_user_per_day,
                    },
                    {
                      field: REPLY_CAP_FIELDS.maxPerThreadPerDay,
                      label: "Max per thread / day",
                      ...REPLY_CAP_BOUNDS.max_per_thread_per_day,
                      value: prov.reply_caps.max_per_thread_per_day,
                    },
                    {
                      field: REPLY_CAP_FIELDS.minSecondsBetween,
                      label: "Min seconds between",
                      ...REPLY_CAP_BOUNDS.min_seconds_between,
                      value: prov.reply_caps.min_seconds_between,
                    },
                    {
                      field: REPLY_CAP_FIELDS.batchMaxPerRun,
                      label: "Batch max per run",
                      ...REPLY_CAP_BOUNDS.batch_max_per_run,
                      value: prov.reply_caps.batch_max_per_run,
                    },
                  ]}
                  onChange={(field, value) =>
                    setProvider(id, {
                      ...prov,
                      reply_caps: { ...prov.reply_caps, [field]: value },
                    })
                  }
                />
              </div>
              <div className="md:col-span-2">
                <p className="mb-1.5 text-sm font-medium leading-none">Targets</p>
                <TargetsToggleRow
                  idPrefix={`provider_${id}`}
                  value={prov.targets}
                  onChange={(next) => setProvider(id, { ...prov, targets: next })}
                  disabled={disabled}
                />
              </div>
            </CardContent>
          </Card>
        );
      })}

      <SafetyRulesFields
        value={editedDoc.safety_rules}
        onChange={(next) => onChange({ ...editedDoc, safety_rules: next })}
        disabled={disabled}
      />

      <ContentStyleFields
        value={editedDoc.content_style}
        onChange={(next) => onChange({ ...editedDoc, content_style: next })}
        disabled={disabled}
      />

      {!validation.ok ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">Validation issues</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {validation.issues.map((issue) => (
                <li key={`${issue.path}__${issue.reason}`}>
                  <code className="text-xs">{issue.path}</code>{" — "}
                  <span className="text-destructive">{issue.reason}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <div className="sticky bottom-0 z-10 flex items-center justify-between gap-3 rounded-md border border-border/40 bg-background/95 p-3 shadow-sm backdrop-blur">
        <div className="flex items-center gap-3 text-sm">
          {dirty ? (
            <Badge variant="secondary">{localDiff.length} change(s) pending</Badge>
          ) : (
            <span className="text-muted-foreground">{UI_TEXT.noChanges}</span>
          )}
          {!writesEnabled ? (
            <Badge variant="warning">Writes disabled on server</Badge>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled={!dirty || disabled} onClick={onReset}>
            {UI_TEXT.resetButton}
          </Button>
          <Button disabled={!canPreview} onClick={onPreview}>
            {UI_TEXT.previewButton}
          </Button>
        </div>
      </div>
    </div>
  );
}
