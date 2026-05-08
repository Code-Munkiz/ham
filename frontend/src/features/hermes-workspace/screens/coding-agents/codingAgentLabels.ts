/**
 * Single source of normie-friendly user-facing copy for the Coding Agents
 * screen. The product rule for this MVP: never expose internal vocabulary
 * (provider keys, registry status, audit sinks, ControlPlaneRun, JSONL,
 * mission_handling, planned_candidate, operator phases) in primary UI.
 *
 * If a label changes, the change is intentional and must be reflected here
 * AND in `__tests__/codingAgentLabels.test.ts`.
 */

export const CODING_AGENT_LABELS = {
  surfaceTitle: "Coding agents",
  surfaceSubtitle:
    "Hand off a coding task. Preview what will happen, approve the launch, then track progress.",
  newTaskCta: "New task",
  previewCta: "Preview",
  approveCta: "Approve launch",
  cancelCta: "Cancel",
  trackProgressCta: "Track progress",

  readinessReady: "Ready",
  readinessNeedsSetup: "Needs setup",

  statusInProgress: "In progress",
  statusComplete: "Complete",
  statusFailed: "Failed",
  statusRunning: "Running",
  statusNeedsAttention: "Needs attention",

  chooserTitle: "Pick a coding agent",
  chooserSubtitle: "Different agents are good at different things. Pick what fits this task.",
  chooserCursorTitle: "Cursor — start a coding task",
  chooserCursorBody:
    "Hand off a freeform coding task to Cursor in the cloud. Best when you want changes made for you.",
  chooserDroidTitle: "Factory Droid — audit your repository",
  chooserDroidBody:
    "Run an approved read-only audit on a project. Best when you want findings, not changes.",

  auditTitle: "Factory Droid audit",
  auditCta: "New audit",
  auditTaskLabel: "What should we look at?",
  auditTaskPlaceholder:
    "Describe what you want audited. For example: review for security risks, or summarize how the auth flow works.",
  auditReadOnlyPill: "Read-only — no files will be changed.",
  auditPreviewIntro: "This is what we'll look at when you approve.",
  auditLaunchedToast: "Audit started. Track progress below.",
  auditNoRunsTitle: "No audits yet",
  auditNoRunsBody: "Approve a new audit to see it here.",

  formProjectLabel: "Project",
  formProjectPlaceholder: "Pick a project",
  formRepositoryLabel: "Repository",
  formRepositoryPlaceholder: "https://github.com/your-org/your-repo",
  formTaskLabel: "What should the agent do?",
  formTaskPlaceholder: "Describe the change. Be specific about files, behavior, and acceptance.",
  formBranchLabel: "Branch or commit (optional)",
  formBranchNamePrLabel: "Branch name for the change (optional)",
  formAutoCreatePrLabel: "Open a pull request when the agent finishes",

  setupNeededTitle: "Connect a coding agent to start",
  setupNeededBody:
    "You need to connect Cursor in Settings before you can launch a new task. Add the API key under Settings, then come back here.",
  setupNeededOpenSettings: "Open settings",

  previewHeading: "Review before launching",
  previewIntro: "This is what will happen when you approve.",

  noProjectsTitle: "Add a project first",
  noProjectsBody: "Register at least one project before you can launch a coding task on it.",

  launchedToast: "Launched. Track progress under Operations.",
  launchFailedToast: "Couldn't launch. Check the details and try again.",
  /** After a failed launch when Cursor credentials are invalid or rejected upstream. */
  launchCursorConnectionHelp:
    "Cursor rejected the launch. Check the Cursor connection in Settings.",
  /** When Ham could not authorize the request (session). */
  launchSessionAuthorizeHelp: "We could not authorize that launch. Sign in again, then try again.",

  validationProjectRequired: "Pick a project.",
  validationRepositoryRequired: "Repository URL is required.",
  validationTaskRequired: "Describe what the agent should do.",

  /** Secondary mention only — never primary. */
  comingSoonNote:
    "More coding agents are on the way. Today you can hand off to Cursor or run an approved audit with Factory Droid.",
} as const;

export type CodingAgentLabels = typeof CODING_AGENT_LABELS;
