/**
 * HAM ManagedMission APIs — list/detail (read-only) + agent sync (server proxies Cursor).
 */

import { hamApiFetch } from "@/lib/ham/api";

const BASE = "/api/cursor/managed";
const CURSOR_BASE = "/api/cursor";

export type ManagedMissionLifecycle = "open" | "succeeded" | "failed" | "archived";

/** Public mission shape from GET list/detail and POST .../sync (exclude_none=false on server may include nulls). */
export type ManagedMissionSnapshot = {
  kind: "managed_mission";
  provider?: "cursor";
  title?: string | null;
  task_summary?: string | null;
  mission_registry_id: string;
  cursor_agent_id: string;
  mission_handling?: "managed";
  mission_deploy_approval_mode?: string;
  control_plane_ham_run_id?: string | null;
  uplink_id?: string | null;
  repo_key?: string | null;
  repository_observed?: string | null;
  ref_observed?: string | null;
  branch_name_launch?: string | null;
  mission_lifecycle: ManagedMissionLifecycle;
  cursor_status_last_observed?: string | null;
  status_reason_last_observed?: string | null;
  created_at: string;
  updated_at: string;
  last_server_observed_at: string;
  last_review_severity?: string | null;
  last_review_headline?: string | null;
  last_deploy_state_observed?: string | null;
  last_vercel_mapping_tier?: string | null;
  last_hook_outcome?: string | null;
  last_post_deploy_state?: string | null;
  last_post_deploy_reason_code?: string | null;
  latest_checkpoint?: string | null;
  latest_checkpoint_at?: string | null;
  latest_checkpoint_reason?: string | null;
  progress_events?: {
    kind?: string;
    label?: string;
    at?: string;
    value?: string | null;
  }[];
  artifacts?: {
    kind?: string;
    title?: string;
    url?: string;
  }[];
  outputs_available?: boolean;
  cancel_supported?: boolean;
  error_summary?: string | null;
};

export type ManagedMissionListPayload = {
  kind: "managed_mission_list";
  limit: number;
  missions: ManagedMissionSnapshot[];
};

export type ManagedMissionFeedEvent = {
  id: string;
  time: string;
  kind: string;
  source: string;
  message: string;
  reason_code?: string | null;
  metadata?: Record<string, unknown> | null;
};

/** Server-declared REST projection semantics (not provider-native streaming). */
export type ProviderProjectionInfo = {
  provider?: string;
  mode?: string;
  native_realtime_stream?: boolean;
  status?: string;
  reason?: string | null;
};

export type ManagedMissionFeedPayload = {
  mission_id: string;
  provider: "cursor";
  status: string;
  lifecycle: ManagedMissionLifecycle;
  repo?: string | null;
  ref?: string | null;
  latest_checkpoint?: string | null;
  updated_at?: string | null;
  events: ManagedMissionFeedEvent[];
  artifacts?: { kind?: string; title?: string; url?: string }[];
  pr_url?: string | null;
  cancel_supported?: boolean;
  provider_capabilities?: Record<string, unknown>;
  provider_projection_state?: string;
  provider_projection_reason?: string | null;
  provider_projection?: ProviderProjectionInfo | null;
};

function parseErrorBody(status: number, text: string): string {
  const body = text.trim();
  if (!body) return `HTTP ${status}`;
  try {
    const j = JSON.parse(body) as { detail?: unknown };
    if (typeof j?.detail === "string") return j.detail;
    if (j?.detail != null && typeof j.detail === "object") {
      const o = j.detail as { message?: string; error?: { message?: string } };
      if (typeof o.message === "string") return o.message;
      if (typeof o.error?.message === "string") return o.error.message;
      return JSON.stringify(j.detail).slice(0, 600);
    }
  } catch {
    return body.slice(0, 600);
  }
  return `HTTP ${status}`;
}

export async function fetchManagedMissions(limit = 80): Promise<{
  missions: ManagedMissionSnapshot[];
  error: string | null;
  httpStatus: number | null;
}> {
  try {
    const res = await hamApiFetch(`${BASE}/missions?limit=${encodeURIComponent(String(limit))}`, {
      credentials: "include",
    });
    const text = await res.text();
    if (!res.ok) {
      return { missions: [], error: parseErrorBody(res.status, text), httpStatus: res.status };
    }
    const data = JSON.parse(text) as ManagedMissionListPayload;
    const missions = Array.isArray(data.missions) ? data.missions : [];
    return { missions, error: null, httpStatus: res.status };
  } catch (e) {
    return { missions: [], error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}

export async function fetchManagedMissionDetail(missionRegistryId: string): Promise<{
  mission: ManagedMissionSnapshot | null;
  error: string | null;
  httpStatus: number | null;
}> {
  const id = missionRegistryId.trim();
  if (!id) {
    return { mission: null, error: "Missing mission id", httpStatus: null };
  }
  try {
    const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}`, { credentials: "include" });
    const text = await res.text();
    if (!res.ok) {
      return { mission: null, error: parseErrorBody(res.status, text), httpStatus: res.status };
    }
    const mission = JSON.parse(text) as ManagedMissionSnapshot;
    return { mission, error: null, httpStatus: res.status };
  } catch (e) {
    return { mission: null, error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}

/**
 * Server: Cursor GET agent + observe_mission_from_cursor_payload; returns persisted ManagedMission.
 * Requires Cursor API key on the HAM server and an existing registry row for this agent id.
 */
export async function syncManagedMissionByAgentId(agentId: string): Promise<{
  mission: ManagedMissionSnapshot | null;
  error: string | null;
  httpStatus: number | null;
}> {
  const aid = agentId.trim();
  if (!aid) {
    return { mission: null, error: "Missing Cursor agent id", httpStatus: null };
  }
  try {
    const res = await hamApiFetch(`${CURSOR_BASE}/agents/${encodeURIComponent(aid)}/sync`, {
      method: "POST",
      credentials: "include",
    });
    const text = await res.text();
    if (!res.ok) {
      return { mission: null, error: parseErrorBody(res.status, text), httpStatus: res.status };
    }
    const mission = JSON.parse(text) as ManagedMissionSnapshot;
    return { mission, error: null, httpStatus: res.status };
  } catch (e) {
    return { mission: null, error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}

export async function fetchManagedMissionFeed(missionRegistryId: string): Promise<{
  feed: ManagedMissionFeedPayload | null;
  error: string | null;
  httpStatus: number | null;
}> {
  const id = missionRegistryId.trim();
  if (!id) {
    return { feed: null, error: "Missing mission id", httpStatus: null };
  }
  try {
    const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}/feed`, {
      credentials: "include",
    });
    const text = await res.text();
    if (!res.ok) {
      return { feed: null, error: parseErrorBody(res.status, text), httpStatus: res.status };
    }
    const feed = JSON.parse(text) as ManagedMissionFeedPayload;
    return { feed, error: null, httpStatus: res.status };
  } catch (e) {
    return { feed: null, error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}

export async function postManagedMissionMessage(missionRegistryId: string, message: string): Promise<{
  ok: boolean;
  reasonCode: string | null;
  error: string | null;
  httpStatus: number | null;
}> {
  const id = missionRegistryId.trim();
  const msg = message.trim();
  if (!id) return { ok: false, reasonCode: "mission_not_found", error: "Missing mission id", httpStatus: null };
  if (!msg) return { ok: false, reasonCode: "mission_followup_not_supported", error: "Message is empty", httpStatus: null };
  try {
    const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message: msg }),
    });
    const text = await res.text();
    if (!res.ok) {
      return { ok: false, reasonCode: null, error: parseErrorBody(res.status, text), httpStatus: res.status };
    }
    const data = JSON.parse(text) as { ok?: boolean; reason_code?: string | null };
    return {
      ok: data.ok === true,
      reasonCode: typeof data.reason_code === "string" ? data.reason_code : null,
      error: null,
      httpStatus: res.status,
    };
  } catch (e) {
    return { ok: false, reasonCode: null, error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}

export async function cancelManagedMission(missionRegistryId: string): Promise<{
  ok: boolean;
  reasonCode: string | null;
  error: string | null;
  httpStatus: number | null;
}> {
  const id = missionRegistryId.trim();
  if (!id) return { ok: false, reasonCode: "mission_not_found", error: "Missing mission id", httpStatus: null };
  try {
    const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
      credentials: "include",
    });
    const text = await res.text();
    if (!res.ok) {
      return { ok: false, reasonCode: null, error: parseErrorBody(res.status, text), httpStatus: res.status };
    }
    const data = JSON.parse(text) as { ok?: boolean; reason_code?: string | null };
    return {
      ok: data.ok === true,
      reasonCode: typeof data.reason_code === "string" ? data.reason_code : null,
      error: null,
      httpStatus: res.status,
    };
  } catch (e) {
    return { ok: false, reasonCode: null, error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}
