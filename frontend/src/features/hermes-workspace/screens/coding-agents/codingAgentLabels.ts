/**
 * Single source of normie-friendly user-facing copy for coding-agent adapters,
 * readiness pills, and Builder Studio preference strings. Builder wizards use
 * `builderStudioLabels.ts`. Never expose internal vocabulary (provider keys,
 * registry status, audit sinks, ControlPlaneRun, JSONL, mission_handling,
 * planned_candidate, operator phases) in primary UI.
 *
 * If a label changes, reflect it in `__tests__/codingAgentLabels.test.ts`.
 * Task launch UI was retired from a dedicated route — builds start from chat.
 */

export const CODING_AGENT_LABELS = {
  surfaceTitle: "Builder Studio",
  surfaceSubtitle:
    "Configure builders and defaults; start builds and handoffs from workspace chat after HAM proposes a plan.",
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
  /** Shown when no project is selected for the audits list. */
  auditNoProjectTitle: "Pick a project to see audits",
  auditNoProjectBody: "Choose a project, then we'll show recent audits for it here.",
  /** Shown when the audits list could not load for any reason. Never includes raw HTTP/path text. */
  auditRunsLoadFailed: "Couldn't load recent audits. Try again.",
  /** Mapped from preview/launch 404 — service hasn't picked up the new lane yet. */
  auditDeploymentNotReady:
    "Factory Droid audit is not available in this deployment yet. Try again after the service finishes updating.",
  /** Mapped from preview validation issues. Never leaks Pydantic / FastAPI detail. */
  auditPreviewValidationFailed:
    "We couldn't review that audit. Check your project and prompt, then try again.",
  /** Generic preview/launch failure — keeps the user moving without raw error text. */
  auditPreviewFailed: "Factory Droid could not start the audit. Please try again.",

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
    "You can hand off to Cursor, run an approved audit with Factory Droid, or build with OpenCode (open / bring-your-own model) when it's configured.",

  chooserOpencodeTitle: "OpenCode — open / bring-your-own model build",
  chooserOpencodeBody:
    "Build in a managed workspace using your own model credentials. Best when you want to try a different model or run open-weight builds.",
  opencodeProviderName: "OpenCode",
  opencodeReadinessNotConfigured: "OpenCode is not configured on this host yet.",
  opencodeReadinessReady: "Ready when configured",

  // Builder Studio — connection list (primary surface)
  builderConnectionsTitle: "Builder connections",
  builderConnectionsSubtitle:
    "See whether each builder is connected and ready. HAM still chooses the best option per task in chat and asks before running.",

  builderConnectionClaudeTitle: "Claude",
  builderConnectionClaudeSubtitle: "Deep reasoning builder for complex codebase edits.",

  builderConnectionCursorTitle: "Cursor",
  builderConnectionCursorSubtitle: "Connected repo builder for pull-request workflows.",

  builderConnectionFactoryTitle: "Factory Droid",
  builderConnectionFactorySubtitle: "Controlled builder for structured, auditable workflows.",

  builderConnectionOpencodeSubtitle:
    "Open builder for managed workspace builds and bring-your-own-model workflows.",

  connectionStatusChecking: "Checking…",
  connectionStatusNeedsCredentials: "Needs credentials",
  connectionStatusNeedsConnection: "Needs connection",
  connectionStatusNeedsRunner: "Needs runner",
  connectionStatusUnavailable: "Unavailable",
  connectionStatusFree: "Free",

  actionConnectClaude: "Connect Claude",
  actionConnectCursor: "Connect Cursor",
  actionConnectFactory: "Connect Factory",
  actionConfigureModelAccess: "Configure model access",
  actionManage: "Manage",

  // Reserved for a future advanced / operator-only preferences surface (not shown in default Builder Studio).
  settingsPanelTitle: "Builder settings",
  settingsPanelSubtitle: "Choose which builders HAM may use and how it picks among them.",
  settingsFactoryDroidLabel: "Controlled managed builder",
  settingsFactoryDroidDescription: "Let HAM choose Factory Droid for controlled, auditable builds.",
  settingsClaudeAgentLabel: "Claude",
  settingsClaudeAgentDescription:
    "Deep reasoning builder for complex codebase edits — connect in Settings when available.",
  settingsOpencodeLabel: "Open / bring-your-own-model builder",
  settingsOpencodeDescription:
    "Let HAM choose OpenCode when you have model access configured. Requires model credentials.",
  settingsCursorLabel: "Connected repo builder",
  settingsCursorDescription:
    "Let HAM choose Cursor for connected repository pull-request workflows.",

  settingsPreferenceModeLabel: "How should HAM pick builders?",
  settingsPreferenceModeRecommended: "Let HAM choose the best builder",
  settingsPreferenceModeOpenCustom: "Prefer open / bring-your-own-model builder",
  settingsPreferenceModePremiumReasoning: "Prefer Claude",
  settingsPreferenceModeConnectedRepo: "Prefer connected repo builder",
  settingsPreferenceModePremiumUnavailableHint: "Turn on Claude above to choose this preference.",
  settingsPreferenceModeOpenCustomUnavailableHint:
    "Turn on open / bring-your-own-model builder above to choose this preference.",
  settingsPreferenceModeConnectedRepoUnavailableHint:
    "Turn on connected repo builder above to choose this preference.",
  settingsStatusReady: "Ready",
  settingsStatusNeedsModelAccess: "Needs model access",
  settingsStatusNeedsConnectedRepo: "Needs connected repo",
  settingsStatusNotAvailable: "Not available on this host",

  settingsSaveError: "Couldn't save builder settings. Try again.",
  settingsLoadError: "Couldn't load builder settings.",

  // Builder connection detail panel (inline in Builder Studio)
  builderPanelOpenDetailsPrefix: "Open details for",
  builderPanelRowDetailHint: "Details",
  builderPanelCloseAria: "Close builder details",
  builderPanelGoodForHeading: "Good for",
  builderPanelRequiresHeading: "Requires",
  builderPanelStatusHeading: "Current status",
  builderPanelNextStepHeading: "Safe next step",
  builderPanelNextStepCaption:
    "Take the primary action to connect or adjust this builder. Additional links open related workspace settings when you need more control.",

  /** Pipe-separated; split for bullet list. Never “Claude Code.” */
  builderPanelClaudeGoodFor: "Complex edits|Reasoning-heavy refactors|Codebase understanding",
  builderPanelClaudeRequires:
    "Claude Agent must be enabled with valid Anthropic or Claude credentials, or backend authentication.",
  builderPanelPrimaryManageClaude: "Manage Claude",
  builderPanelPrimaryConnectClaude: "Connect Claude",

  builderPanelCursorGoodFor:
    "Repo-connected changes|Pull-request-oriented work|Cursor-authenticated workflows",
  builderPanelCursorRequires: "A Cursor connection and an eligible workspace or repository state.",
  builderPanelPrimaryManageCursor: "Manage Cursor",
  builderPanelPrimaryConnectCursor: "Connect Cursor",

  builderPanelFactoryGoodFor:
    "Deterministic tasks|Repository audits|Controlled, structured workflows",
  builderPanelFactoryRequires: "Factory entitlement, runner availability, and project readiness.",
  builderPanelPrimarySetupRunner: "Set up runner",
  builderPanelPrimaryManageFactory: "Manage Factory",
  builderPanelSecondaryOpenProjects: "Open projects",

  builderPanelOpencodeGoodFor:
    "Open or free builder workflows|Managed workspace builds|Bring-your-own-model and provider workflows",
  builderPanelOpencodeRequires:
    "OpenCode runtime or exec access. Model access is optional for some modes; provider-specific flows may need keys handled in settings.",
  builderPanelSecondaryOpenModelSettings: "Open model settings",

  builderPanelSecondaryConnectedTools: "Open connected tools",
} as const;

export type CodingAgentLabels = typeof CODING_AGENT_LABELS;
