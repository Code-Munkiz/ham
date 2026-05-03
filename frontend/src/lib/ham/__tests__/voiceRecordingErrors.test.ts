/**
 * Phase C.1 baseline test: pure-function mapping of MediaRecorder /
 * getUserMedia errors to user-facing strings. No DOM, no Clerk, no fetch.
 *
 * The function under test never echoes raw browser strings into the UI,
 * so these tests pin the exact user-visible copy for the most common
 * failure shapes plus an unrecognized-error fallback.
 */
import { describe, expect, it } from "vitest";
import { mapMediaStreamErrorToUserMessage } from "@/lib/ham/voiceRecordingErrors";

describe("mapMediaStreamErrorToUserMessage", () => {
  it("returns the no-microphone copy for NotFoundError", () => {
    const out = mapMediaStreamErrorToUserMessage({ name: "NotFoundError" });
    expect(out).toBe(
      "No microphone was found. Connect or enable a microphone, then try again.",
    );
  });

  it("returns the permission-blocked copy for NotAllowedError", () => {
    const out = mapMediaStreamErrorToUserMessage({ name: "NotAllowedError" });
    expect(out).toBe(
      "Microphone permission is blocked. Allow microphone access in your browser settings.",
    );
  });

  it("returns the in-use copy for NotReadableError", () => {
    const out = mapMediaStreamErrorToUserMessage({ name: "NotReadableError" });
    expect(out).toBe(
      "Your microphone is already in use or unavailable. Close other apps using it and try again.",
    );
  });

  it("returns the unsupported copy for TypeError", () => {
    const out = mapMediaStreamErrorToUserMessage({ name: "TypeError" });
    expect(out).toBe(
      "Microphone recording is not supported in this browser context.",
    );
  });

  it("returns the secure-context copy when the message mentions secure context", () => {
    const out = mapMediaStreamErrorToUserMessage({
      name: "Whatever",
      message: "Cannot use this API outside a secure context",
    });
    expect(out).toBe(
      "Voice input requires a secure (HTTPS) connection in this browser.",
    );
  });

  it("falls back to the generic copy for null", () => {
    const out = mapMediaStreamErrorToUserMessage(null);
    expect(out).toBe(
      "Voice input could not start. Check browser site permissions and OS microphone access.",
    );
  });

  it("falls back to the generic copy for an unrecognized error name", () => {
    const out = mapMediaStreamErrorToUserMessage({ name: "WeirdNewError" });
    expect(out).toBe(
      "Voice input could not start. Check browser site permissions and OS microphone access.",
    );
  });
});
