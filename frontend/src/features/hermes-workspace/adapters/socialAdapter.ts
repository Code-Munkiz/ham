/**
 * HAM /api/social — read-only social provider status facade.
 */

import { hamApiFetch } from "@/lib/ham/api";

import { workspaceApiPending } from "../lib/workspaceHamApiState";

const BASE = "/api/social";

export type SocialBridge = { status: "ready" } | { status: "pending"; detail: string };

export type SocialProvider = {
  id: string;
  label: string;
  status: "active" | "setup_required" | "blocked" | "coming_soon";
  configured: boolean;
  coming_soon: boolean;
  enabled_lanes: string[];
};

export type XProviderStatus = {
  provider_id: "x";
  label: "X";
  overall_readiness: "ready" | "limited" | "blocked" | "setup_required";
  readiness_reasons: string[];
  emergency_stop: { enabled: boolean };
  dry_run_defaults: {
    global_dry_run: boolean;
    controller_dry_run: boolean;
    reactive_dry_run: boolean;
    reactive_batch_dry_run: boolean;
  };
  broadcast_lane: {
    enabled: boolean;
    controller_enabled: boolean;
    live_controller_enabled: boolean;
    dry_run_available: boolean;
    live_configured: boolean;
    execution_allowed_now: boolean;
    reasons: string[];
  };
  reactive_lane: {
    enabled: boolean;
    inbox_discovery_enabled: boolean;
    dry_run_enabled: boolean;
    live_canary_enabled: boolean;
    batch_enabled: boolean;
    reasons: string[];
  };
  last_autonomous_post: Record<string, unknown> | null;
  last_reactive_reply: Record<string, unknown> | null;
  cap_cooldown_summary: {
    broadcast_daily_cap: number;
    broadcast_daily_used: number;
    broadcast_daily_remaining: number;
    broadcast_per_run_cap: number;
    broadcast_min_spacing_minutes: number;
    reactive_max_replies_per_15m: number;
    reactive_max_replies_per_hour: number;
    reactive_max_replies_per_user_per_day: number;
    reactive_max_replies_per_thread_per_day: number;
    reactive_min_seconds_between_replies: number;
    reactive_batch_max_replies_per_run: number;
  };
  paths: {
    execution_journal_path: string;
    audit_log_path: string;
  };
  read_only: boolean;
  mutation_attempted: boolean;
};

export type XCapabilities = {
  provider_id: "x";
  live_read_available: boolean;
  live_model_available: boolean;
  broadcast_dry_run_available: boolean;
  broadcast_live_available: boolean;
  broadcast_apply_available: boolean;
  reactive_inbox_discovery_available: boolean;
  reactive_dry_run_available: boolean;
  reactive_reply_canary_available: boolean;
  reactive_batch_available: boolean;
  reactive_reply_apply_available: boolean;
  reactive_batch_apply_available: boolean;
  live_apply_available: boolean;
  read_only: boolean;
};

export type XSetupChecklist = {
  provider_id: "x";
  items: { id: string; label: string; ok: boolean }[];
  feature_flags: Record<string, boolean>;
  read_only: boolean;
};

export type XSetupSummary = {
  provider_id: "x";
  provider_configured: boolean;
  overall_readiness: "ready" | "limited" | "blocked" | "setup_required";
  missing_requirement_ids: string[];
  ready_for_dry_run: boolean;
  ready_for_confirmed_live_reply: boolean;
  ready_for_reactive_batch: boolean;
  ready_for_broadcast: boolean;
  required_connections: Record<string, boolean>;
  lane_readiness: Record<string, Record<string, unknown>>;
  safe_identifiers: Record<string, string>;
  caps_cooldowns: Record<string, number>;
  feature_flags: Record<string, boolean>;
  recommended_next_steps: string[];
  read_only: boolean;
  mutation_attempted: boolean;
};

export type XJournalSummary = {
  provider_id: "x";
  journal_path: string;
  total_count_scanned: number;
  malformed_count: number;
  counts_by_execution_kind: Record<string, number>;
  latest_broadcast_post: Record<string, unknown> | null;
  latest_reactive_reply: Record<string, unknown> | null;
  recent_items: Record<string, unknown>[];
  bounds: {
    max_recent_items: number;
    max_rows_scanned: number;
    max_bytes_scanned: number;
  };
  read_only: boolean;
  mutation_attempted: boolean;
};

export type XAuditSummary = {
  provider_id: "x";
  audit_path: string;
  total_count_scanned: number;
  malformed_count: number;
  counts_by_event_type: Record<string, number>;
  latest_audit_ids: string[];
  recent_events: Record<string, unknown>[];
  bounds: {
    max_recent_events: number;
    max_rows_scanned: number;
    max_bytes_scanned: number;
  };
  read_only: boolean;
  mutation_attempted: boolean;
};

export type SocialPreviewKind = "reactive_inbox" | "reactive_batch_dry_run" | "broadcast_preflight";

export type SocialPreviewResponse = {
  provider_id: "x";
  preview_kind: SocialPreviewKind;
  status: "completed" | "blocked" | "failed";
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
  proposal_digest: string | null;
  read_only: boolean;
};

export type SocialReactiveReplyApplyResponse = {
  provider_id: "x";
  apply_kind: "reactive_reply";
  status: "blocked" | "executed" | "failed";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  provider_status_code: number | null;
  provider_post_id: string | null;
  execution_kind: string;
  audit_ids: string[];
  journal_path: string;
  audit_path: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type SocialReactiveBatchApplyResponse = {
  provider_id: "x";
  apply_kind: "reactive_batch";
  status: "blocked" | "completed" | "stopped" | "failed";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  attempted_count: number;
  executed_count: number;
  failed_count: number;
  blocked_count: number;
  provider_post_ids: string[];
  execution_kind: string;
  audit_ids: string[];
  journal_path: string;
  audit_path: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type SocialBroadcastApplyResponse = {
  provider_id: "x";
  apply_kind: "broadcast_post";
  status: "blocked" | "executed" | "failed";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  provider_status_code: number | null;
  provider_post_id: string | null;
  execution_kind: string;
  audit_ids: string[];
  journal_path: string;
  audit_path: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type SocialSnapshot = {
  providers: SocialProvider[];
  xStatus: XProviderStatus;
  xCapabilities: XCapabilities;
  xSetup: XSetupChecklist;
  xSetupSummary: XSetupSummary;
  xJournal: XJournalSummary;
  xAudit: XAuditSummary;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await hamApiFetch(path, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postPreview<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const res = await hamApiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const socialAdapter = {
  description: "HAM /api/social — read-only social provider status",

  async loadSnapshot(): Promise<{ snapshot: SocialSnapshot | null; bridge: SocialBridge; error?: string }> {
    try {
      const [providers, xStatus, xCapabilities, xSetup, xSetupSummary, xJournal, xAudit] = await Promise.all([
        getJson<{ providers?: SocialProvider[] }>(`${BASE}/providers`),
        getJson<XProviderStatus>(`${BASE}/providers/x/status`),
        getJson<XCapabilities>(`${BASE}/providers/x/capabilities`),
        getJson<XSetupChecklist>(`${BASE}/providers/x/setup/checklist`),
        getJson<XSetupSummary>(`${BASE}/providers/x/setup/summary`),
        getJson<XJournalSummary>(`${BASE}/providers/x/journal/summary`),
        getJson<XAuditSummary>(`${BASE}/providers/x/audit/summary`),
      ]);
      return {
        snapshot: {
          providers: Array.isArray(providers.providers) ? providers.providers : [],
          xStatus,
          xCapabilities,
          xSetup,
          xSetupSummary,
          xJournal,
          xAudit,
        },
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        snapshot: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewInboxDiscovery(): Promise<{ preview: SocialPreviewResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      return {
        preview: await postPreview<SocialPreviewResponse>(`${BASE}/providers/x/reactive/inbox/preview`),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewReactiveBatchDryRun(
    candidates: Record<string, unknown>[] = [],
  ): Promise<{ preview: SocialPreviewResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      return {
        preview: await postPreview<SocialPreviewResponse>(`${BASE}/providers/x/reactive/batch/dry-run`, {
          candidates,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewBroadcastPreflight(): Promise<{ preview: SocialPreviewResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      return {
        preview: await postPreview<SocialPreviewResponse>(`${BASE}/providers/x/broadcast/preflight`),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async sendOneLiveReply(input: {
    proposalDigest: string;
    confirmationPhrase: string;
    operatorToken: string;
    clientRequestId?: string;
  }): Promise<{ apply: SocialReactiveReplyApplyResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/providers/x/reactive/reply/apply`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ham-Operator-Authorization": `Bearer ${input.operatorToken}`,
        },
        credentials: "include",
        body: JSON.stringify({
          proposal_digest: input.proposalDigest,
          confirmation_phrase: input.confirmationPhrase,
          client_request_id: input.clientRequestId,
        }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = (await res.json()) as { detail?: { error?: { message?: string } } | string };
          if (typeof body.detail === "string") detail = body.detail;
          else if (body.detail?.error?.message) detail = body.detail.error.message;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      return { apply: (await res.json()) as SocialReactiveReplyApplyResponse, bridge: { status: "ready" } };
    } catch (e) {
      return {
        apply: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async sendLiveReactiveBatch(input: {
    proposalDigest: string;
    confirmationPhrase: string;
    operatorToken: string;
    clientRequestId?: string;
  }): Promise<{ apply: SocialReactiveBatchApplyResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/providers/x/reactive/batch/apply`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ham-Operator-Authorization": `Bearer ${input.operatorToken}`,
        },
        credentials: "include",
        body: JSON.stringify({
          proposal_digest: input.proposalDigest,
          confirmation_phrase: input.confirmationPhrase,
          client_request_id: input.clientRequestId,
        }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = (await res.json()) as { detail?: { error?: { message?: string } } | string };
          if (typeof body.detail === "string") detail = body.detail;
          else if (body.detail?.error?.message) detail = body.detail.error.message;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      return { apply: (await res.json()) as SocialReactiveBatchApplyResponse, bridge: { status: "ready" } };
    } catch (e) {
      return {
        apply: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async sendOneLivePost(input: {
    proposalDigest: string;
    confirmationPhrase: string;
    operatorToken: string;
    clientRequestId?: string;
  }): Promise<{ apply: SocialBroadcastApplyResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/providers/x/broadcast/apply`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ham-Operator-Authorization": `Bearer ${input.operatorToken}`,
        },
        credentials: "include",
        body: JSON.stringify({
          proposal_digest: input.proposalDigest,
          confirmation_phrase: input.confirmationPhrase,
          client_request_id: input.clientRequestId,
        }),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = (await res.json()) as { detail?: { error?: { message?: string } } | string };
          if (typeof body.detail === "string") detail = body.detail;
          else if (body.detail?.error?.message) detail = body.detail.error.message;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      return { apply: (await res.json()) as SocialBroadcastApplyResponse, bridge: { status: "ready" } };
    } catch (e) {
      return {
        apply: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
} as const;
