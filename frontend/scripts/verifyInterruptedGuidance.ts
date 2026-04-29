import assert from "node:assert/strict";
import {
  interruptedAssistantView,
  INTERRUPTED_SUFFIX,
  INTERRUPTED_EMPTY,
} from "../src/features/hermes-workspace/screens/chat/interruptedAssistantView";

function run(): void {
  const interrupted = interruptedAssistantView(`partial reply${INTERRUPTED_SUFFIX}`);
  assert.equal(interrupted.interrupted, true);
  assert.equal(interrupted.visibleContent, "partial reply");
  assert.equal(interrupted.visibleContent.includes("Connection interrupted. Ask me to continue."), false);

  const interruptedEmpty = interruptedAssistantView(INTERRUPTED_EMPTY);
  assert.equal(interruptedEmpty.interrupted, true);
  assert.equal(interruptedEmpty.visibleContent, "");

  const normal = interruptedAssistantView("normal completed assistant response");
  assert.equal(normal.interrupted, false);
  assert.equal(normal.visibleContent, "normal completed assistant response");

  console.log("Interrupted guidance parsing checks passed.");
}

run();
