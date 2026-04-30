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
  reactive_inbox_discovery_available: boolean;
  reactive_dry_run_available: boolean;
  reactive_reply_canary_available: boolean;
  reactive_batch_available: boolean;
  live_apply_available: boolean;
  read_only: boolean;
};

export type XSetupChecklist = {
  provider_id: "x";
  items: { id: string; label: string; ok: boolean }[];
  feature_flags: Record<string, boolean>;
  read_only: boolean;
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

export type SocialSnapshot = {
  providers: SocialProvider[];
  xStatus: XProviderStatus;
  xCapabilities: XCapabilities;
  xSetup: XSetupChecklist;
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
      const [providers, xStatus, xCapabilities, xSetup, xJournal, xAudit] = await Promise.all([
        getJson<{ providers?: SocialProvider[] }>(`${BASE}/providers`),
        getJson<XProviderStatus>(`${BASE}/providers/x/status`),
        getJson<XCapabilities>(`${BASE}/providers/x/capabilities`),
        getJson<XSetupChecklist>(`${BASE}/providers/x/setup/checklist`),
        getJson<XJournalSummary>(`${BASE}/providers/x/journal/summary`),
        getJson<XAuditSummary>(`${BASE}/providers/x/audit/summary`),
      ]);
      return {
        snapshot: {
          providers: Array.isArray(providers.providers) ? providers.providers : [],
          xStatus,
          xCapabilities,
          xSetup,
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
} as const;
