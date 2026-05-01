import {
  parseWorkspaceCreativeImageIntent,
  parseWorkspaceImageGenerationIntent,
} from "../src/features/hermes-workspace/screens/chat/imageGenerationIntent";

function mustMatchTextToImage(prompt: string) {
  const p = parseWorkspaceImageGenerationIntent(prompt);
  if (!p) throw new Error(`Expected text-to-image routing for: ${prompt}`);
}

function mustNotMatchTextToImage(prompt: string) {
  if (parseWorkspaceImageGenerationIntent(prompt) !== null) {
    throw new Error(`Did not expect text-to-image routing for: ${prompt}`);
  }
}

function mustMatchImageToImage(prompt: string) {
  const c = parseWorkspaceCreativeImageIntent(prompt, { hasImageAttachment: true });
  if (!c || c.kind !== "image_to_image") {
    throw new Error(`Expected image-to-image routing (with attachment) for: ${prompt}`);
  }
}

function mustNotMatchImageToImage(prompt: string) {
  const c = parseWorkspaceCreativeImageIntent(prompt, { hasImageAttachment: true });
  if (c?.kind === "image_to_image") {
    throw new Error(`Did not expect image-to-image routing for: ${prompt}`);
  }
}

for (const s of [
  "show me a picture of a futuristic HAM dashboard",
  "create an image of a robot monkey architect",
  "generate a logo for HAM",
  "draw a clean icon of a cloud agent",
  "make a banner with a neural network and terminal",
]) {
  mustMatchTextToImage(s);
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
  mustNotMatchTextToImage(s);
}

// Prompt stripping: prefixed phrase removed
const stripped = parseWorkspaceImageGenerationIntent("create an image of a robot monkey architect");
if (!stripped || !/robot monkey/i.test(stripped)) {
  throw new Error(`prompt extraction failed: ${JSON.stringify(stripped)}`);
}

// Phase 2G.3 — when an image is attached, edit-style phrases route to image-to-image.
for (const s of [
  "make this more modern",
  "turn this into a logo",
  "change the background to a city skyline",
  "create a variation of this image",
  "use this as reference and make it cleaner",
  "edit this image to look like a SaaS hero",
  "restyle the attached screenshot with a dark theme",
]) {
  mustMatchImageToImage(s);
}

// Same strings must not switch to text-to-image when no attachment (ambiguous / deictic).
for (const s of [
  "make this more modern",
  "turn this into a logo",
  "use this as reference and make it cleaner",
]) {
  mustNotMatchTextToImage(s);
}

// Vision / analysis must not become image-to-image when an image is attached.
for (const s of [
  "what is in this image?",
  "describe this screenshot",
  "analyze this attached image",
  "read this UI",
  "summarize the attached image",
]) {
  mustNotMatchImageToImage(s);
}

console.log("run-image-intent-checks: ok");
