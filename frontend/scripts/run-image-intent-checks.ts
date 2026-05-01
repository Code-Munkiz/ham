import { parseWorkspaceImageGenerationIntent } from "../src/features/hermes-workspace/screens/chat/imageGenerationIntent";

function mustMatch(prompt: string) {
  const p = parseWorkspaceImageGenerationIntent(prompt);
  if (!p) throw new Error(`Expected image-generation routing for: ${prompt}`);
}

function mustNotMatch(prompt: string) {
  if (parseWorkspaceImageGenerationIntent(prompt) !== null) {
    throw new Error(`Did not expect image-generation routing for: ${prompt}`);
  }
}

for (const s of [
  "show me a picture of a futuristic HAM dashboard",
  "create an image of a robot monkey architect",
  "generate a logo for HAM",
  "draw a clean icon of a cloud agent",
  "make a banner with a neural network and terminal",
]) {
  mustMatch(s);
}

for (const s of [
  "what is in this picture?",
  "describe the attached image",
  "can you read this screenshot?",
  "this image shows a bug",
  "analyze this UI",
  "draw conclusions from the spreadsheet",
  "generate art of this screenshot",
]) {
  mustNotMatch(s);
}

// Prompt stripping: prefixed phrase removed
const stripped = parseWorkspaceImageGenerationIntent("create an image of a robot monkey architect");
if (!stripped || !/robot monkey/i.test(stripped)) {
  throw new Error(`prompt extraction failed: ${JSON.stringify(stripped)}`);
}

console.log("run-image-intent-checks: ok");
