/**
 * Locks normal product-flow copy that must stay free of internal-runtime,
 * provider, and infrastructure tokens (Hermes identity / Cloud Agent /
 * Cloud Run / GCP / Firestore) outside diagnostic/admin contexts.
 *
 * Covers VAL-FRONTEND-001..003 and VAL-FRONTEND-008.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import type { ManagedMissionSnapshot } from "@/features/hermes-workspace/adapters/managedMissionsAdapter";
import {
  missionTitle,
  providerLabel,
} from "@/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel";

const REPO_ROOT = resolve(__dirname, "../../../../..");

function readFrontend(p: string): string {
  return readFileSync(resolve(REPO_ROOT, "frontend", p), "utf-8");
}

function snapshot(partial: Partial<ManagedMissionSnapshot>): ManagedMissionSnapshot {
  return {
    kind: "managed_mission",
    mission_registry_id: "m1",
    cursor_agent_id: "bc-1",
    provider: "cursor",
    title: null,
    task_summary: null,
    repository_observed: null,
    ref_observed: null,
    mission_lifecycle: "open",
    latest_checkpoint: null,
    cursor_status_last_observed: null,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    last_server_observed_at: "2024-01-01T00:00:00Z",
    ...partial,
  } as ManagedMissionSnapshot;
}

describe("Managed missions panel helpers", () => {
  it("defaults missionTitle to a Cursor mission product label, never Cloud Agent", () => {
    expect(missionTitle(snapshot({}))).toBe("Cursor mission");
    expect(missionTitle(snapshot({ title: "  " }))).toBe("Cursor mission");
    expect(missionTitle(snapshot({ title: "Custom title" }))).toBe("Custom title");
  });

  it("providerLabel renders Cursor-branded text for both cursor and non-cursor lanes", () => {
    expect(providerLabel(snapshot({ provider: "cursor" }))).toBe("Cursor");
    expect(providerLabel(snapshot({ provider: undefined }))).toBe("Cursor mission");
  });
});

describe("Frontend product boundary copy (normal flows)", () => {
  it("WorkspaceOpenRouterModelPicker uses Default model wording, not Hermes identity", () => {
    const src = readFrontend(
      "src/features/hermes-workspace/screens/chat/WorkspaceOpenRouterModelPicker.tsx",
    );
    expect(src).toContain("Default model");
    expect(src).not.toMatch(/Hermes Agent \/ Default/);
    expect(src).not.toMatch(/Hermes default/);
  });

  it("WorkspaceChatScreen does not surface Hermes identity in normal model fallbacks", () => {
    const src = readFrontend("src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx");
    expect(src).not.toMatch(/Hermes Agent \/ Default/);
    expect(src).not.toMatch(/Use Hermes default/);
  });

  it("UnifiedSettings normal helper copy uses workspace chat, not Hermes workspace chat", () => {
    const src = readFrontend("src/components/workspace/UnifiedSettings.tsx");
    expect(src).not.toMatch(/Hermes workspace chat/);
  });

  it("Mission/conductor/chat surfaces use Cursor wording instead of generic Cloud Agent", () => {
    const panel = readFrontend(
      "src/features/hermes-workspace/components/WorkspaceManagedMissionsLivePanel.tsx",
    );
    expect(panel).toContain("Live Cursor missions");
    expect(panel).toContain("No Cursor missions yet");
    expect(panel).not.toMatch(/Live Cloud Agent missions/);
    expect(panel).not.toMatch(/No Cloud Agent missions yet/);
    expect(panel).not.toMatch(/Cloud Agent mission(?! history)/);

    const conductor = readFrontend(
      "src/features/hermes-workspace/screens/conductor/WorkspaceConductorScreen.tsx",
    );
    expect(conductor).toContain("Cursor missions");
    expect(conductor).not.toMatch(/Cloud Agent missions/);

    const chat = readFrontend("src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx");
    expect(chat).not.toMatch(/: "Cloud Agent"\}/);
  });

  it("ApiKeysPanel header in UnifiedSettings drops Cursor Cloud Agent product label", () => {
    const src = readFrontend("src/components/workspace/UnifiedSettings.tsx");
    expect(src).toContain("Used for Cursor missions launched from this workspace.");
    expect(src).not.toMatch(/Used for Cursor Cloud Agent missions/);
    expect(src).not.toMatch(/Cursor Cloud Agent missions are unavailable/);
  });

  it("Files/Connection helper copy avoids Cloud Run in normal user flows", () => {
    const files = readFrontend(
      "src/features/hermes-workspace/screens/files/WorkspaceFilesScreen.tsx",
    );
    expect(files).not.toMatch(/not Cloud Run/);
    expect(files).toContain("not the hosted API");

    const connection = readFrontend(
      "src/features/hermes-workspace/screens/settings/WorkspaceConnectionSection.tsx",
    );
    expect(connection).not.toMatch(/not Cloud Run/);
    expect(connection).toContain("not the hosted API");

    const chat = readFrontend("src/features/hermes-workspace/screens/chat/WorkspaceChatScreen.tsx");
    expect(chat).not.toMatch(/chat history on Cloud Run/);
    expect(chat).toContain("chat history on the hosted API");
  });
});
