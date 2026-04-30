/** Operator-facing copy: who owns what for Cursor Cloud Agent + HAM managed missions (Phase A honesty). */

export const MANAGED_MISSION_TRUTH_TABLE_ROWS: ReadonlyArray<{
  concern: string;
  cursor: string;
  ham: string;
}> = [
  {
    concern: "Execution (code, tools, VM)",
    cursor: "Cursor Cloud Agent runs in Cursor’s environment.",
    ham: "HAM records and surfaces status; it does not execute the agent’s work.",
  },
  {
    concern: "Lifecycle / conversation truth",
    cursor: "Cursor APIs are upstream for the live agent.",
    ham: "HAM keeps an observed ManagedMission snapshot (poll + mapping), not a second source of execution truth.",
  },
  {
    concern: "mission_registry_id",
    cursor: "Not a Cursor concept.",
    ham: "HAM-stable id for this mission row — use it in Workspace, chat links, and support.",
  },
  {
    concern: "Deploy approval default",
    cursor: "N/A",
    ham: "Snapshotted at managed create when project_id was set; not live-synced if the project default changes later.",
  },
  {
    concern: "Feed in the browser",
    cursor: "Browser does not call Cursor for the mission feed.",
    ham: "HAM API only (`/api/cursor/managed/missions/…/feed`); server may use REST refresh or SDK bridge.",
  },
  {
    concern: "Hermes critic on every turn",
    cursor: "N/A",
    ham: "Not automatic — bridge/main.py critique is a separate path; bounded mission critique is later roadmap.",
  },
];

export const MANAGED_MISSION_CHAT_BANNER_NOTE =
  "Cursor runs the agent; HAM stores an observed mission record and policy edges (deploy default is create-time when set). Not the same as Hermes bridge critique on every turn.";
