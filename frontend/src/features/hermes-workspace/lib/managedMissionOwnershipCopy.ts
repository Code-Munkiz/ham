/**
 * Short operator hints for managed Cloud Agent missions.
 * Authoritative rows live in GET /api/cursor/managed/missions/{id}/truth — do not duplicate as static truth tables.
 */

/** Mission-mode chat banner — subtle; full matrix is in Live missions / detail + /truth. */
export const MANAGED_MISSION_CHAT_OWNERSHIP_HINT =
  "HAM tracks mission state and feed; Cursor runs the cloud agent.";
