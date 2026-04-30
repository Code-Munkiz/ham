/** Runtime checks for mission feed transcript join / collapse — run via `npx tsx scripts/verify-mission-feed-transcript.ts` from `frontend/`. */
import assert from "node:assert";
import {
  collapseAdjacentDuplicateTranscriptNoise,
  missionFeedTranscriptFromEvents,
  joinTranscriptChunk,
  postJoinTranscriptText,
} from "../src/features/hermes-workspace/utils/missionFeedTranscript";
import type { ManagedMissionFeedEvent } from "../src/features/hermes-workspace/adapters/managedMissionsAdapter";
import { cursorCloudAgentWebHref, isBcCursorAgentId } from "../src/features/hermes-workspace/utils/cursorCloudAgentWeb";

assert.strictEqual(joinTranscriptChunk("", "hello"), "hello");
assert.strictEqual(joinTranscriptChunk("hi", "there"), "hi there");
assert.strictEqual(joinTranscriptChunk("word", "!"), "word!");
assert.strictEqual(joinTranscriptChunk("open(", "args"), "open(args");
assert.strictEqual(joinTranscriptChunk("a", "(b"), "a(b");
assert.strictEqual(joinTranscriptChunk("end.", "Next"), "end. Next");

const glued = joinTranscriptChunk("The user wants me", "toimplement");
assert.ok(glued.includes(" "), "word boundary should insert space");
const repaired = postJoinTranscriptText(glued);
assert.ok(repaired.includes("to implement"), `expected 'to implement' in: ${repaired}`);

const statusEvents: ManagedMissionFeedEvent[] = [1, 2, 3, 4, 5].map((i) => ({
  id: `e${i}`,
  time: `2026-01-01T00:00:0${i}Z`,
  kind: "provider_status",
  source: "cursor",
  message: "Cursor status: RUNNING.",
}));
const tr = missionFeedTranscriptFromEvents(statusEvents, "open", "live");
const st = tr.find((x) => x.type === "status");
assert.ok(st, "expected one merged status row");
assert.ok(st!.label.includes("×5"), "expected repeat count");

assert.strictEqual(isBcCursorAgentId("bc-abc123def456"), true);
assert.strictEqual(isBcCursorAgentId("not-bc"), false);
assert.strictEqual(isBcCursorAgentId("bc-x"), false);
const href = cursorCloudAgentWebHref("bc-testid");
assert.ok(href.startsWith("https://cursor.com/agents/"), href);
assert.ok(href.includes("app=code"), href);
assert.ok(!href.includes("api.cursor.com"));

const mixed = collapseAdjacentDuplicateTranscriptNoise([
  { type: "status", id: "a", label: "Cursor status: RUNNING.", time: "t1", eventIds: ["1"] },
  { type: "status", id: "b", label: "Cursor status: RUNNING.", time: "t2", eventIds: ["2"] },
  { type: "tool", id: "c", label: "read", status: "complete", eventIds: ["3"] },
]);
assert.strictEqual(mixed.length, 2);
assert.ok(mixed[0].type === "status" && mixed[0].label.includes("×2"));

console.log("mission-feed-transcript verify: ok");
