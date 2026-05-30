import {
  BUILDER_WORKBENCH_EMPTY_SUBTITLE,
  BUILDER_WORKBENCH_EMPTY_TITLE,
} from "@/lib/ham/builderFirstRunOnboarding";
import { sanitizeWorkbenchProjectAccessMessage } from "@/lib/ham/workbenchProjectMessages";

export type WorkbenchPreviewPhase =
  | "no_project"
  | "no_source"
  | "preparing"
  | "source_ready"
  | "starting"
  | "ready"
  | "error";

export type PreviewPrimaryState = {
  title: string;
  subtitle: string;
};

export type PreviewPrimaryStateContext = {
  previewMode?: "local" | "cloud" | null;
  previewMessage?: string | null;
  hasBackendSource: boolean;
  iframeProxyError?: string | null;
  iframeProxyWarmupPaused?: boolean;
  authSessionRefreshing?: boolean;
  cloudPreviewDisconnected?: boolean;
  activityTitle?: string | null;
  rawError?: string | null;
};

export const FORBIDDEN_USER_COPY_PATTERN =
  /safe_edit_low|ham_droid_exec_token|droid exec|\bargv\b|runner url|preview_proxy|builder-artifact|gcs|kubernetes|\bpod\b|controlplanerun|stack trace|authorization:|bearer /i;

/** Normie-friendly status pill label (never raw phase ids). */
export function previewPhaseUserLabel(phase: WorkbenchPreviewPhase): string {
  switch (phase) {
    case "no_project":
      return "No project";
    case "no_source":
      return "Getting started";
    case "preparing":
      return "Preparing";
    case "source_ready":
      return "Almost ready";
    case "starting":
      return "Starting";
    case "ready":
      return "Ready";
    case "error":
      return "Needs attention";
    default:
      return "Preview";
  }
}

function isProjectNotFoundError(message: string | null | undefined): boolean {
  const text = (message || "").toLowerCase();
  return text.includes("unknown project_id") || text.includes("project_not_found");
}

/** Strip internal infrastructure tokens from preview fetch/runtime errors. */
export function sanitizePreviewFetchError(message: string | null | undefined): string | null {
  const raw = (message || "").trim();
  if (!raw) return null;
  if (/\b404\b/i.test(raw) || /HTTP\s*404/i.test(raw)) {
    return "Preview status is not available yet.";
  }
  if (/\b502\b/i.test(raw) || /\bBAD_GATEWAY\b/i.test(raw)) {
    return "Preview is still preparing. HAM will keep checking.";
  }
  if (
    /PREVIEW_PROXY_UPSTREAM_UNAVAILABLE/i.test(raw) ||
    /PREVIEW_PROXY_TIMEOUT/i.test(raw) ||
    /PREVIEW_PROXY_NOT_CONFIGURED/i.test(raw) ||
    /PREVIEW_PROXY_FAILED/i.test(raw) ||
    /PREVIEW_PROXY_WARMUP/i.test(raw)
  ) {
    return "Preview is still warming up. HAM will keep retrying until it is ready.";
  }
  if (/http\s+\d+/i.test(raw) || /\b(401|403|429|500|503)\b/.test(raw)) {
    return "Preview could not refresh right now. Try again in a moment.";
  }
  if (FORBIDDEN_USER_COPY_PATTERN.test(raw) || raw.includes("{") || raw.includes("}")) {
    return "Preview could not start. Try again in a moment.";
  }
  return raw;
}

/** User-facing error line under the primary preview title. */
export function sanitizePreviewStateError(
  rawError: string | null | undefined,
  previewMessage?: string | null,
): string {
  if (isProjectNotFoundError(rawError || previewMessage || "")) {
    return "This project is no longer available. Pick another project or create a new one.";
  }
  const sanitized =
    sanitizePreviewFetchError(rawError) ||
    sanitizePreviewFetchError(previewMessage) ||
    sanitizeWorkbenchProjectAccessMessage(String(rawError || previewMessage || "").trim());
  if (!sanitized || FORBIDDEN_USER_COPY_PATTERN.test(sanitized)) {
    return "Preview could not start. Try again in a moment.";
  }
  return sanitized;
}

export function buildPreviewPrimaryState(
  phase: WorkbenchPreviewPhase,
  ctx: PreviewPrimaryStateContext,
): PreviewPrimaryState {
  if (phase === "no_project" || phase === "no_source") {
    return {
      title: BUILDER_WORKBENCH_EMPTY_TITLE,
      subtitle: BUILDER_WORKBENCH_EMPTY_SUBTITLE,
    };
  }

  if (phase === "preparing") {
    return {
      title: "HAM is preparing your preview.",
      subtitle: "Hang tight while HAM sets up your project files.",
    };
  }

  if (phase === "source_ready" || phase === "starting") {
    if (ctx.authSessionRefreshing) {
      return {
        title: "Preview is almost ready.",
        subtitle: "Your session is refreshing. HAM will retry automatically.",
      };
    }
    if (ctx.iframeProxyWarmupPaused || ctx.iframeProxyError === "PREVIEW_PROXY_WARMUP") {
      return {
        title: "Preview is almost ready.",
        subtitle:
          "Preview is still warming up. Use Try again, or wait a few seconds while HAM retries.",
      };
    }
    if (ctx.previewMode === "cloud") {
      return {
        title: "Preview is almost ready.",
        subtitle: ctx.cloudPreviewDisconnected
          ? "Cloud preview is not available in this environment yet. Your code is still in the Code tab."
          : "Your project files are ready. The hosted preview will appear here when the environment finishes starting.",
      };
    }
    return {
      title: "Preview is almost ready.",
      subtitle: ctx.cloudPreviewDisconnected
        ? "Connect a local dev server URL in Open details, or keep building in chat."
        : "Connect a local preview URL when your dev server is running, or open details for setup help.",
    };
  }

  if (phase === "error") {
    if (ctx.iframeProxyError === "PREVIEW_PROXY_FAILED") {
      return {
        title: "Preview could not start.",
        subtitle:
          "The preview environment finished building but the app did not load. Try again or make a small edit in chat.",
      };
    }
    return {
      title: "Preview could not start.",
      subtitle: ctx.hasBackendSource
        ? "Your project files are saved in the Code tab. Try again or open details for setup help."
        : sanitizePreviewStateError(ctx.rawError, ctx.previewMessage),
    };
  }

  return { title: "", subtitle: "" };
}

/** Safe one-line status for optional details panel (no ids or URLs). */
export function sanitizePreviewDetailsStatus(message: string | null | undefined): string {
  const raw = (message || "").trim();
  if (!raw) {
    return "Preview status is updating.";
  }
  const sanitized = sanitizePreviewFetchError(raw) || sanitizePreviewStateError(raw, null);
  if (!sanitized || FORBIDDEN_USER_COPY_PATTERN.test(sanitized)) {
    return "Preview status is updating.";
  }
  return sanitized;
}

export function previewUserCopyLooksSafe(text: string): boolean {
  return !FORBIDDEN_USER_COPY_PATTERN.test(text);
}
