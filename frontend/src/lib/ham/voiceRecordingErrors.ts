/**
 * User-facing copy for MediaRecorder / getUserMedia failures (no raw browser strings in UI).
 */

export function mapMediaStreamErrorToUserMessage(err: unknown): string {
  if (err == null) {
    return "Voice input could not start. Check browser site permissions and OS microphone access.";
  }

  const e = err as DOMException & { message?: string };
  const name = typeof e.name === "string" ? e.name : "";
  const rawMsg = typeof e.message === "string" ? e.message : "";
  const blob = `${name} ${rawMsg}`.toLowerCase();

  if (
    name === "NotFoundError" ||
    name === "DevicesNotFoundError" ||
    blob.includes("device not found") ||
    blob.includes("requested device not found")
  ) {
    return "No microphone was found. Connect or enable a microphone, then try again.";
  }

  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "Microphone permission is blocked. Allow microphone access in your browser settings.";
  }

  if (name === "TypeError" || name === "NotSupportedError") {
    return "Microphone recording is not supported in this browser context.";
  }

  if (name === "NotReadableError" || name === "TrackStartError") {
    return "Your microphone is already in use or unavailable. Close other apps using it and try again.";
  }

  if (name === "OverconstrainedError") {
    return "The selected microphone settings are not supported.";
  }

  if (name === "AbortError") {
    return "Microphone recording was interrupted. Try again.";
  }

  if (blob.includes("secure context")) {
    return "Voice input requires a secure (HTTPS) connection in this browser.";
  }
  if (name === "SecurityError") {
    return "Microphone permission is blocked. Allow microphone access in your browser settings.";
  }

  return "Voice input could not start. Check browser site permissions and OS microphone access.";
}
