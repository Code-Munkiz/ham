/**
 * HAM GET /api/cursor/managed/missions — durable ManagedMission rows (server-side store).
 * Read-only list for Workspace Operations / Conductor live runtime panels.
 */

import { hamApiFetch } from "@/lib/ham/api";

const BASE = "/api/cursor/managed";

export type ManagedMissionLifecycle = "open" | "succeeded" | "failed" | "archived";

/** Subset of fields the UI displays; API may include additional keys. */
export type ManagedMissionSnapshot = {
  kind: "managed_mission";
  mission_registry_id: string;
  cursor_agent_id: string;
  mission_lifecycle: ManagedMissionLifecycle;
  cursor_status_last_observed: string | null;
  status_reason_last_observed: string | null;
  created_at: string;
  updated_at: string;
  last_server_observed_at: string;
  repository_observed?: string | null;
  ref_observed?: string | null;
  branch_name_launch?: string | null;
  last_review_headline?: string | null;
  control_plane_ham_run_id?: string | null;
};

export type ManagedMissionListPayload = {
  kind: "managed_mission_list";
  limit: number;
  missions: ManagedMissionSnapshot[];
};

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
      let detail = `HTTP ${res.status}`;
      const body = text.trim();
      if (body) {
        try {
          const j = JSON.parse(body) as { detail?: unknown };
          if (typeof j?.detail === "string") detail = j.detail;
          else if (j?.detail != null) detail = JSON.stringify(j.detail).slice(0, 500);
        } catch {
          detail = body.slice(0, 500);
        }
      }
      return { missions: [], error: detail, httpStatus: res.status };
    }
    const data = JSON.parse(text) as ManagedMissionListPayload;
    const missions = Array.isArray(data.missions) ? data.missions : [];
    return { missions, error: null, httpStatus: res.status };
  } catch (e) {
    return { missions: [], error: e instanceof Error ? e.message : String(e), httpStatus: null };
  }
}
