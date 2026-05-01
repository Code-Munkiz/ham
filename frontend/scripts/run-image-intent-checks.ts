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

/** Composer may set hasImageAttachment; text-only generation must still match after normalization. */
function mustMatchTextToImageWithComposerAttachment(prompt: string) {
  const c = parseWorkspaceCreativeImageIntent(prompt, { hasImageAttachment: true });
  if (!c || c.kind !== "text_to_image") {
    throw new Error(`Expected text-to-image with attachment hint for: ${prompt}`);
  }
}

function mustBeNullCreativeWithAttachment(prompt: string) {
  const c = parseWorkspaceCreativeImageIntent(prompt, { hasImageAttachment: true });
  if (c !== null) {
    throw new Error(`Expected no creative-media intent with attachment hint for: ${prompt}`);
  }
}

for (const s of [
  "show me a picture of a futuristic HAM dashboard",
  "create an image of a robot monkey architect",
  "create an image of a realistic monkey eating a banana",
  "show me a picture of a monkey eating a banana",
  "generate a photo of a monkey eating a banana",
  "generate a realistic photo of a monkey eating a banana",
  "make a realistic image of a monkey eating a banana",
  "make a picture of a monkey eating a banana",
  "draw a monkey eating a banana",
  "generate a logo for HAM",
  "draw a clean icon of a cloud agent",
  "make a banner with a neural network and terminal",
  // Wake-word / polite prefix normalization → same matchers as stripped probe
  "ham show me a picture of a real banana",
  "ham, show me a picture of a real banana",
  "hey ham show me a real image of a banana",
  "hey ham, show me a real image of a banana",
  "ham: create a real image of a banana",
  "please generate a photo of a banana",
  "can you make a realistic image of a monkey eating a banana",
  "could you draw a monkey eating a banana",
  "I want you to create an image of a robot monkey architect",
]) {
  mustMatchTextToImage(s);
}

for (const s of ["ham show me a picture of a real banana"]) {
  mustMatchTextToImageWithComposerAttachment(s);
}

for (const s of [
  "what is in this picture?",
  "what is in this image?",
  "describe this picture",
  "describe this image.",
  "analyze this screenshot",
  "can you read this picture?",
  "describe the attached image",
  "can you read this screenshot?",
  "this image shows a bug",
  "analyze this UI",
  "draw conclusions from the spreadsheet",
  "generate art of this screenshot",
  // Same analysis intent with leading invocation — must stay off generation
  "ham what is in this image?",
  "ham describe this picture",
  "ham analyze this screenshot",
  "please describe the attached image",
  "could you analyze this UI screenshot?",
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
  "ham make this more modern",
  "please edit this image to look bolder",
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
  "ham what is in this image?",
  "please analyze this screenshot",
]) {
  mustNotMatchImageToImage(s);
}

for (const s of ["ham what is in this image?", "can you read this picture?"]) {
  mustBeNullCreativeWithAttachment(s);
}

console.log("run-image-intent-checks: ok");
