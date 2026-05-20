import { afterEach, describe, expect, it } from "vitest";

import {
  readWorkspaceLastChatSessionId,
  writeWorkspaceLastChatSessionId,
  workspaceLastSessionStorageKey,
} from "../workspaceChatSessionStorage";

describe("workspaceChatSessionStorage", () => {
  const workspaceId = "ws_test_stream_lock";

  afterEach(() => {
    window.localStorage.removeItem(workspaceLastSessionStorageKey(workspaceId));
  });

  it("clears persisted session id when starting a new chat (null write)", () => {
    writeWorkspaceLastChatSessionId(workspaceId, "391d70cd-5c2e-44e8-9ec2-60b8c9d3ba5a");
    expect(readWorkspaceLastChatSessionId(workspaceId)).toBe(
      "391d70cd-5c2e-44e8-9ec2-60b8c9d3ba5a",
    );

    writeWorkspaceLastChatSessionId(workspaceId, null);
    expect(readWorkspaceLastChatSessionId(workspaceId)).toBeNull();
  });
});
