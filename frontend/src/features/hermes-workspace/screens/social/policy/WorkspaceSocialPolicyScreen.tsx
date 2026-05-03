import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  applyPolicy,
  loadAudit,
  loadHistory,
  loadPolicy,
  newClientProposalId,
  previewPolicy,
  SocialPolicyApiError,
} from "../../../adapters/socialPolicyAdapter";
import { APPLY_CONFIRMATION_PHRASE } from "./lib/policyConstants";
import { UI_TEXT, labelForError } from "./lib/policyCopy";
import { hasPolicyChanges } from "./lib/policyDiff";
import type {
  SocialPolicyApplyResponse,
  SocialPolicyAuditEnvelope,
  SocialPolicyBackupListItem,
  SocialPolicyDoc,
  SocialPolicyEndpointResponse,
  SocialPolicyPreviewResponse,
  SocialPolicyServerError,
} from "./lib/policyTypes";
import { PolicyEditor } from "./PolicyEditor";
import { PolicyDiffView } from "./PolicyDiffView";
import { PolicyApplyModal, type ApplyState } from "./PolicyApplyModal";
import { PolicyHistoryPanel } from "./PolicyHistoryPanel";
import { PolicyAuditPanel } from "./PolicyAuditPanel";

const DEFAULT_DOC: SocialPolicyDoc = {
  schema_version: 1,
  persona: { persona_id: "ham-canonical", persona_version: 1 },
  content_style: {
    tone: "warm",
    length_preference: "standard",
    emoji_policy: "sparingly",
    nature_tags: [],
  },
  safety_rules: {
    blocked_topics: [],
    block_links: true,
    min_relevance: 0.75,
    consecutive_failure_stop: 2,
    policy_rejection_stop: 10,
  },
  providers: {
    x: {
      provider_id: "x",
      posting_mode: "off",
      reply_mode: "off",
      posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
      reply_caps: {
        max_per_15m: 5,
        max_per_hour: 20,
        max_per_user_per_day: 3,
        max_per_thread_per_day: 5,
        min_seconds_between: 60,
        batch_max_per_run: 1,
      },
      posting_actions_allowed: [],
      targets: [],
    },
    telegram: {
      provider_id: "telegram",
      posting_mode: "off",
      reply_mode: "off",
      posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
      reply_caps: {
        max_per_15m: 5,
        max_per_hour: 20,
        max_per_user_per_day: 3,
        max_per_thread_per_day: 5,
        min_seconds_between: 60,
        batch_max_per_run: 1,
      },
      posting_actions_allowed: [],
      targets: [],
    },
    discord: {
      provider_id: "discord",
      posting_mode: "off",
      reply_mode: "off",
      posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
      reply_caps: {
        max_per_15m: 5,
        max_per_hour: 20,
        max_per_user_per_day: 3,
        max_per_thread_per_day: 5,
        min_seconds_between: 60,
        batch_max_per_run: 1,
      },
      posting_actions_allowed: [],
      targets: [],
    },
  },
  autopilot_mode: "off",
  live_autonomy_armed: false,
};

function deepClone<T>(value: T): T {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value)) as T;
}

type Tab = "edit" | "history" | "audit";

export function WorkspaceSocialPolicyScreen(): React.ReactElement {
  const [params, setParams] = useSearchParams();
  const tabParam = params.get("tab");
  const tab: Tab = tabParam === "history" || tabParam === "audit" ? tabParam : "edit";

  const [endpoint, setEndpoint] = React.useState<SocialPolicyEndpointResponse | null>(null);
  const [loadError, setLoadError] = React.useState<SocialPolicyServerError | null>(null);
  const [loadingPolicy, setLoadingPolicy] = React.useState<boolean>(true);

  const [editedDoc, setEditedDoc] = React.useState<SocialPolicyDoc | null>(null);
  const [loadedDoc, setLoadedDoc] = React.useState<SocialPolicyDoc | null>(null);

  const [preview, setPreview] = React.useState<SocialPolicyPreviewResponse | null>(null);
  const [previewError, setPreviewError] = React.useState<SocialPolicyServerError | null>(null);
  const [previewBusy, setPreviewBusy] = React.useState<boolean>(false);

  const [applyOpen, setApplyOpen] = React.useState<boolean>(false);
  const [applyState, setApplyState] = React.useState<ApplyState>({ kind: "idle" });

  const [history, setHistory] = React.useState<SocialPolicyBackupListItem[]>([]);
  const [historyLoading, setHistoryLoading] = React.useState<boolean>(false);
  const [historyError, setHistoryError] = React.useState<string | null>(null);

  const [audits, setAudits] = React.useState<SocialPolicyAuditEnvelope[]>([]);
  const [auditLoading, setAuditLoading] = React.useState<boolean>(false);
  const [auditError, setAuditError] = React.useState<string | null>(null);

  const clientProposalIdRef = React.useRef<string>(newClientProposalId());

  const refresh = React.useCallback(async () => {
    setLoadingPolicy(true);
    setLoadError(null);
    try {
      const res = await loadPolicy();
      setEndpoint(res);
      const baseDoc = res.policy ?? DEFAULT_DOC;
      setLoadedDoc(deepClone(baseDoc));
      setEditedDoc((current) => current ?? deepClone(baseDoc));
    } catch (err) {
      if (err instanceof SocialPolicyApiError) {
        setLoadError({ status: err.status, code: err.code, message: err.message });
      } else {
        setLoadError({ status: 0, code: "UNKNOWN", message: "Failed to load policy." });
      }
    } finally {
      setLoadingPolicy(false);
    }
  }, []);

  const refreshHistory = React.useCallback(async () => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const res = await loadHistory();
      setHistory(res.backups ?? []);
    } catch (err) {
      const msg =
        err instanceof SocialPolicyApiError ? err.message : "Failed to load history.";
      setHistoryError(msg);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshAudit = React.useCallback(async () => {
    setAuditLoading(true);
    setAuditError(null);
    try {
      const res = await loadAudit();
      setAudits(res.audits ?? []);
    } catch (err) {
      const msg = err instanceof SocialPolicyApiError ? err.message : "Failed to load audit.";
      setAuditError(msg);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    if (tab === "history") void refreshHistory();
    if (tab === "audit") void refreshAudit();
  }, [tab, refreshHistory, refreshAudit]);

  function setTab(next: Tab): void {
    const sp = new URLSearchParams(params);
    sp.set("tab", next);
    setParams(sp, { replace: true });
  }

  async function onPreview(): Promise<void> {
    if (!editedDoc) return;
    setPreviewBusy(true);
    setPreviewError(null);
    try {
      const res = await previewPolicy({
        changes: { policy: editedDoc },
        clientProposalId: clientProposalIdRef.current,
      });
      setPreview(res);
    } catch (err) {
      if (err instanceof SocialPolicyApiError) {
        setPreviewError({ status: err.status, code: err.code, message: err.message });
      } else {
        setPreviewError({ status: 0, code: "UNKNOWN", message: "Preview failed." });
      }
    } finally {
      setPreviewBusy(false);
    }
  }

  function onReset(): void {
    if (!loadedDoc) return;
    setEditedDoc(deepClone(loadedDoc));
    setPreview(null);
    setPreviewError(null);
  }

  function onOpenApply(): void {
    setApplyState({ kind: "idle" });
    setApplyOpen(true);
  }

  async function onSubmitApply(input: { confirmationPhrase: string; writeToken: string }): Promise<void> {
    if (!preview || !editedDoc) return;
    if (preview.live_autonomy_change) return;
    if (input.confirmationPhrase !== APPLY_CONFIRMATION_PHRASE) return;

    setApplyState({ kind: "applying" });
    try {
      const result: SocialPolicyApplyResponse = await applyPolicy({
        changes: { policy: editedDoc },
        baseRevision: preview.base_revision,
        confirmationPhrase: input.confirmationPhrase,
        writeToken: input.writeToken,
        clientProposalId: clientProposalIdRef.current,
      });
      setApplyState({ kind: "success", result });
      // Refresh policy + history; reset editor and proposal id.
      clientProposalIdRef.current = newClientProposalId();
      setEditedDoc(deepClone(result.effective_after));
      setLoadedDoc(deepClone(result.effective_after));
      setPreview(null);
      void refresh();
      void refreshHistory();
      void refreshAudit();
    } catch (err) {
      if (err instanceof SocialPolicyApiError) {
        const env: SocialPolicyServerError = {
          status: err.status,
          code: err.code,
          message: err.message,
        };
        if (err.code === "SOCIAL_POLICY_REVISION_CONFLICT") {
          setApplyState({ kind: "revision_conflict", error: env });
        } else {
          setApplyState({ kind: "error", error: env });
        }
      } else {
        setApplyState({
          kind: "error",
          error: { status: 0, code: "UNKNOWN", message: "Apply failed." },
        });
      }
    }
  }

  async function onReloadAndKeepEdits(): Promise<void> {
    await refresh();
    setApplyOpen(false);
    setPreview(null);
  }

  const writesEnabled = endpoint?.writes_enabled === true;
  const liveTokenPresent = endpoint?.live_apply_token_present === true;
  const dirty = hasPolicyChanges(loadedDoc, editedDoc);

  return (
    <div className="flex flex-col gap-4 p-4">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold">{UI_TEXT.screenTitle}</h1>
            <p className="text-sm text-muted-foreground">{UI_TEXT.screenSubtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/workspace/social"
              className="text-sm text-muted-foreground underline hover:text-foreground"
            >
              ← Back to Social cockpit
            </Link>
            <Button variant="outline" size="sm" onClick={() => void refresh()}>
              {UI_TEXT.loadButton}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {endpoint ? (
            <>
              <Badge variant="outline">
                rev {endpoint.revision.slice(0, 12)}…
              </Badge>
              <Badge variant={endpoint.exists ? "secondary" : "outline"}>
                {endpoint.exists ? "policy on disk" : "no policy on disk"}
              </Badge>
              <Badge variant={writesEnabled ? "success" : "warning"}>
                {writesEnabled ? "writes enabled" : "writes disabled"}
              </Badge>
              <Badge variant={liveTokenPresent ? "warning" : "outline"}>
                {liveTokenPresent ? "live token present" : "live token absent"}
              </Badge>
              {dirty ? <Badge variant="secondary">unsaved edits</Badge> : null}
            </>
          ) : null}
        </div>
        {loadError ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive">
            {labelForError(loadError)}
          </div>
        ) : null}
        {endpoint && !endpoint.exists ? (
          <div className="rounded-md border border-border/40 bg-muted/30 p-2 text-xs">
            {UI_TEXT.noPolicyOnDisk}
          </div>
        ) : null}
        {endpoint && !endpoint.policy && endpoint.exists ? (
          <div className="rounded-md border border-border/40 bg-muted/30 p-2 text-xs">
            {UI_TEXT.invalidDocBanner}
          </div>
        ) : null}
        {!writesEnabled && endpoint ? (
          <div className="rounded-md border border-border/40 bg-muted/30 p-2 text-xs">
            {UI_TEXT.writesDisabledBanner}
          </div>
        ) : null}
      </header>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList>
          <TabsTrigger value="edit">{UI_TEXT.tabsEdit}</TabsTrigger>
          <TabsTrigger value="history">{UI_TEXT.tabsHistory}</TabsTrigger>
          <TabsTrigger value="audit">{UI_TEXT.tabsAudit}</TabsTrigger>
        </TabsList>

        <TabsContent value="edit" className="flex flex-col gap-4">
          {loadingPolicy || !editedDoc || !loadedDoc ? (
            <p className="text-sm text-muted-foreground">{UI_TEXT.loading}</p>
          ) : (
            <PolicyEditor
              loadedDoc={loadedDoc}
              editedDoc={editedDoc}
              onChange={setEditedDoc}
              onPreview={onPreview}
              onReset={onReset}
              writesEnabled={writesEnabled}
              disabled={previewBusy || applyState.kind === "applying"}
            />
          )}
          {previewError ? (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive">
              {labelForError(previewError)}: {previewError.message}
            </div>
          ) : null}
          {preview ? (
            <PolicyDiffView
              preview={preview}
              applyDisabled={
                preview.diff.length === 0 ||
                preview.live_autonomy_change ||
                !writesEnabled
              }
              applyDisabledReason={
                preview.live_autonomy_change
                  ? "live autonomy change blocked"
                  : preview.diff.length === 0
                    ? "no changes"
                    : !writesEnabled
                      ? "writes disabled"
                      : undefined
              }
              onApply={onOpenApply}
              onCancel={() => setPreview(null)}
            />
          ) : null}
        </TabsContent>

        <TabsContent value="history">
          <PolicyHistoryPanel
            backups={history}
            loading={historyLoading}
            errorMessage={historyError}
          />
        </TabsContent>

        <TabsContent value="audit">
          <PolicyAuditPanel
            audits={audits}
            loading={auditLoading}
            errorMessage={auditError}
          />
        </TabsContent>
      </Tabs>

      {preview ? (
        <PolicyApplyModal
          open={applyOpen}
          preview={preview}
          writesEnabled={writesEnabled}
          state={applyState}
          onApply={(input) => void onSubmitApply(input)}
          onClose={() => {
            setApplyOpen(false);
            // If we just succeeded, reset state for next time.
            if (applyState.kind === "success") {
              setApplyState({ kind: "idle" });
            }
          }}
          onReloadAndKeepEdits={() => void onReloadAndKeepEdits()}
        />
      ) : null}
    </div>
  );
}

