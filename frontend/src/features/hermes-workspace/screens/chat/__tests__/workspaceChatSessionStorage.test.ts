import { afterEach, describe, expect, it } from "vitest";

import {
  readWorkspaceLastChatSessionId,
  workspaceLastSessionStorageKey,
  writeWorkspaceLastChatSessionId,
} from "../workspaceChatSessionStorage";

describe("workspace chat session storage", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("uses legacy key when workspace is absent", () => {
    expect(workspaceLastSessionStorageKey(null)).toBe("hww.chat.lastSessionId");
    expect(workspaceLastSessionStorageKey("   ")).toBe("hww.chat.lastSessionId");
  });

  it("uses a workspace-scoped key when workspace is present", () => {
    expect(workspaceLastSessionStorageKey("ws_123")).toBe("hww.chat.lastSessionId.ws_123");
    expect(workspaceLastSessionStorageKey(" ws_123 ")).toBe("hww.chat.lastSessionId.ws_123");
  });

  it("keeps session ids isolated across workspaces", () => {
    writeWorkspaceLastChatSessionId("ws_a", "sid-a");
    writeWorkspaceLastChatSessionId("ws_b", "sid-b");
    writeWorkspaceLastChatSessionId(null, "sid-legacy");

    expect(readWorkspaceLastChatSessionId("ws_a")).toBe("sid-a");
    expect(readWorkspaceLastChatSessionId("ws_b")).toBe("sid-b");
    expect(readWorkspaceLastChatSessionId(null)).toBe("sid-legacy");
  });

  it("removes only the scoped key when clearing a workspace session", () => {
    writeWorkspaceLastChatSessionId("ws_a", "sid-a");
    writeWorkspaceLastChatSessionId("ws_b", "sid-b");

    writeWorkspaceLastChatSessionId("ws_a", null);

    expect(readWorkspaceLastChatSessionId("ws_a")).toBeNull();
    expect(readWorkspaceLastChatSessionId("ws_b")).toBe("sid-b");
  });
});
