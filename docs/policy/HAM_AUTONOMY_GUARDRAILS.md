# HAM Autonomy Guardrails

Status: policy design, implementation-ready.

This document defines user-selectable automation profiles for HAM control
surfaces and future policy-engine enforcement. It is not executable code.

## Scope

These guardrails apply to automation initiated through HAM surfaces, including
chat, browser-real control, local machine control, scheduled workflows, and
worker/droid launches.

Policy evaluation should treat the selected profile as a maximum autonomy
ceiling. A workflow, tool, connector, or runtime may impose stricter limits.

## Enforcement model

Every automation request should be normalized into an action envelope before
execution:

- `actor`: user, agent, workflow, schedule, or service account.
- `profile`: selected autonomy profile.
- `action_type`: browse, read, write, send, purchase, delete, schedule, auth,
  execute, install, or connect.
- `target`: URL, file path, account, service, recipient set, workflow, device,
  or process.
- `risk_flags`: credential, destructive, external-send, payment, auth-change,
  persistence, privileged-access, bulk, third-party-account, private-data.
- `approval_state`: none, previewed, approved-once, approved-scope,
  approved-session.
- `audit_sink`: append-only destination for the decision and result.

The policy engine should deny by default when an action cannot be classified.

## Automation profiles

### 1. Safe default

Safe default is the baseline for new users, web sessions, shared workspaces, and
unknown machines.

#### Allowed actions

- Read-only browsing and page summarization.
- Read-only repository, project, and run-history inspection.
- Drafting messages, emails, tickets, PR descriptions, and commands without
  sending or executing them.
- Creating local, non-destructive previews of proposed file changes.
- Running explicitly allowlisted read-only diagnostics.
- Opening login pages for the user to complete manually.
- Scheduling reminders that notify the user but do not execute external actions.

#### Approval requirements

- Require explicit per-action approval before any write, send, launch, delete,
  install, login-state change, or external API mutation.
- Require a visible preview for generated content before it can be sent,
  posted, submitted, or saved.
- Require fresh confirmation for each new destination, account, repository,
  domain, recipient, or workflow.
- Session approval must not carry across browser reloads, runtime restarts, or
  device changes.

#### Audit requirements

- Record every denied, previewed, approved, and executed action.
- Include actor, timestamp, profile, action type, target, risk flags, approval
  state, result, and truncated evidence.
- Redact secrets, tokens, cookies, private keys, raw credential fields, and full
  browser profile paths.
- Keep audits append-only and visible to the user.

#### Blocked actions

- Autonomous sending, posting, commenting, purchasing, deleting, installing, or
  changing account settings.
- Background workflow execution without the user present.
- Access to non-allowlisted local paths or arbitrary shell execution.
- Browser profile reuse outside the dedicated HAM profile.
- Any persistence mechanism that survives beyond the approved session.

#### Messaging/send limits

- Draft-only by default.
- At most one explicitly approved send action per user confirmation.
- No bulk messaging, recipient expansion, auto-follow-up, or recurring sends.
- The user must see final text, recipient, account, and destination before send.

#### Login/auth handling

- The user completes all login, MFA, consent, and account-switching steps.
- HAM may navigate to an auth page but must not enter credentials, extract
  tokens, inspect password managers, or copy session cookies.
- OAuth consent scopes must be shown to the user before approval.
- Stored API keys may only be referenced by secret handle, never displayed.

#### Destructive-action handling

- Destructive actions are blocked unless converted into a preview-only plan.
- The plan must list target, impact, rollback option, and required future
  approval.
- Permanent deletion, account closure, branch deletion, production mutation, and
  payment changes require a stricter profile or out-of-band manual action.

#### Workflow scheduling limits

- Reminder-only schedules are allowed.
- Scheduled workflows may gather read-only context and notify the user.
- Scheduled workflows must not write, send, delete, purchase, install, or launch
  agents without a new interactive approval.

### 2. Balanced

Balanced is for trusted users who want useful automation while preserving
approval gates around external impact and risky state changes.

#### Allowed actions

- All Safe default actions.
- Applying low-risk file edits inside an approved project workspace.
- Running tests, linters, builds, and allowlisted local commands.
- Creating draft PRs, tickets, messages, and release notes.
- Sending single-recipient or small-recipient messages after approval.
- Launching bounded worker/droid tasks within approved scope.
- Reading connected service metadata when the user has authorized the connector.
- Scheduling low-risk maintenance workflows with scoped approval.

#### Approval requirements

- Require approval once per scoped workflow for local file writes, test runs,
  build runs, and draft artifact creation.
- Require per-action approval for external sends, postings, comments, issue
  changes, PR creation, production deploys, account changes, payments, installs,
  and destructive actions.
- Require re-approval when scope changes across repository, domain, account,
  credential handle, recipient group, or workflow risk class.
- Require visible diffs for file changes and visible content previews for sends.

#### Audit requirements

- Record every approval decision and executed action.
- Include before/after summaries for file writes and settings changes.
- Store command, cwd, exit code, bounded stdout/stderr, and modified path list
  for local execution.
- Store message body hash, visible preview hash, recipient list, and service for
  send/post actions.
- Make audit records queryable by workflow id and correlation id.

#### Blocked actions

- Credential extraction, token copying, session-cookie export, or password
  manager access.
- Unapproved external messaging, posting, purchasing, deleting, deployment, or
  account mutation.
- Self-installing background agents, startup entries, browser extensions, cron
  jobs, launch agents, services, or scheduled tasks.
- Privilege escalation, security bypass, or access outside approved roots.
- Recipient harvesting or automated contact discovery for outreach.

#### Messaging/send limits

- Default limit: one approved send action per destination and user confirmation.
- Small batch sends require an explicit recipient list preview and approval.
- Maximum recommended batch: 10 recipients unless an administrator sets a lower
  or higher workspace policy.
- No recurring sends without a schedule-specific approval and clear stop date.
- Auto-replies must be draft-only unless a connector-specific policy allows
  approved, narrow-scope replies.

#### Login/auth handling

- The user performs interactive login and MFA.
- HAM may use existing connector tokens through secret handles after the user
  grants connector scope.
- HAM must show account identity before mutating third-party data.
- Token refresh may occur only through the approved connector path.
- Connector scopes should be least privilege and revocable.

#### Destructive-action handling

- Require explicit destructive confirmation with typed target or equivalent
  high-friction acknowledgement.
- Require preview of affected files, records, accounts, repositories, or
  resources.
- Prefer reversible operations: archive, disable, draft, branch, or trash.
- Require rollback instructions or a statement that rollback is unavailable.
- Block destructive actions against production unless workspace policy
  explicitly allows them and the user confirms the environment.

#### Workflow scheduling limits

- Allow scheduled read-only checks, local diagnostics, dependency audits, and
  draft-generation workflows.
- Allow scheduled local writes only inside approved workspace roots and only
  when changes remain draft or branch-scoped.
- Require per-run approval before scheduled workflows send messages, mutate
  external services, deploy, purchase, install, or delete.
- Require owner, scope, next-run time, stop condition, and audit correlation id.

### 3. Power user / local advanced

Power user / local advanced is for experienced users operating a trusted local
runtime. It must not be enabled by default, and it should be unavailable on
untrusted hosted sessions.

#### Allowed actions

- All Balanced actions.
- Broader local file edits within explicitly approved workspace roots.
- Allowlisted shell commands with user-configured risk tiers.
- Local browser-real automation using the dedicated HAM browser profile.
- Local machine-control escalation after browser-real is insufficient.
- Installing approved project dependencies through package managers.
- Running scheduled local workflows with bounded write capability.
- Launching local workers/droids with profile-defined resource and scope limits.

#### Approval requirements

- Require explicit opt-in to the profile on the local device.
- Require arming local control before browser-real or machine-control actions.
- Allow scope approval for repeated low-risk local actions inside the same
  workspace, time window, and workflow id.
- Require per-action approval for external sends, purchases, production deploys,
  credential changes, destructive actions, privileged commands, installs outside
  package managers, and persistence changes.
- Require re-approval after profile changes, policy changes, runtime upgrade,
  account switch, device switch, or expanded workspace root.

#### Audit requirements

- Record full local-control decision traces, bounded screenshots, command
  metadata, file mutation summaries, connector calls, and approval state.
- Store enough evidence to replay policy decisions without storing secrets.
- Include local runtime id, HAM browser profile id, workspace root, workflow id,
  and kill-switch state.
- Preserve IPC channel compatibility and deny raw profile path exposure in
  renderer-visible payloads.
- Support export for user review and incident response.

#### Blocked actions

- Any hard-stop behavior listed in this document.
- Use of the user's default browser profile for automation.
- Broad inbound network listeners for local control.
- Raw credential, cookie, token, private-key, or password-manager access.
- Unapproved persistence, privilege escalation, security bypass, or lateral
  movement.
- Hidden external communication, telemetry, uploads, or data transfer.

#### Messaging/send limits

- User-configurable limits may be higher than Balanced but must remain bounded.
- Require approval for each campaign, recipient set, template, channel, and
  sending account.
- Require unsubscribe/compliance checks where applicable.
- Block unsolicited bulk messaging and recipient scraping regardless of profile.
- Default maximum recommended batch: 50 recipients unless workspace policy
  lowers it.

#### Login/auth handling

- Use trusted local runtime and dedicated HAM browser profile.
- The user completes credential entry, MFA, consent, and account recovery.
- HAM may operate after login only within visible, user-approved session scope.
- Secret handles may be used by allowlisted connectors; raw secret material must
  not be exposed to agents, prompts, renderer payloads, logs, or audits.
- Account switching requires visible confirmation of the active account.

#### Destructive-action handling

- Require typed confirmation or equivalent high-friction approval.
- Require affected-target preview, environment label, reversibility assessment,
  rollback plan, and audit correlation id.
- Require stronger confirmation for production, shared resources, account-level
  resources, or irreversible operations.
- Prefer staged execution: plan, dry run, checkpoint, execute, verify.
- Kill switch must immediately interrupt destructive workflows.

#### Workflow scheduling limits

- Allow recurring local workflows only with explicit owner, schedule, scope,
  stop condition, resource limits, and audit sink.
- Allow bounded local writes within approved roots when workflow scope is stable.
- Require per-run approval for sends, payments, external mutations,
  destructive actions, new installs, privileged commands, and expanded scope.
- Require missed-run and failure behavior to be explicit: skip, retry with cap,
  or notify only.
- Automatically disable schedules after repeated policy denials or audit failures.

## Non-negotiable hard stops

The following actions must be blocked in every profile, for every actor, even
when the user has selected a higher-autonomy mode.

### Credential theft

Block attempts to obtain, reveal, copy, export, infer, transmit, or store raw
passwords, cookies, session tokens, API keys, private keys, recovery codes,
password-manager contents, or MFA secrets outside approved secret-handle flows.

### Malware-like persistence

Block stealthy or deceptive persistence, including unauthorized startup items,
services, launch agents, cron jobs, scheduled tasks, browser extensions,
registry run keys, hidden daemons, watchdogs, self-reinstallers, or persistence
that survives beyond user-approved scope.

### Unauthorized access

Block access to accounts, systems, repositories, devices, files, networks, or
services where the user lacks authorization, where authorization is ambiguous,
or where the action bypasses access controls, rate limits, paywalls, MFA,
licensing, or security policy.

### Spam or unsolicited bulk messaging

Block unsolicited bulk messaging, recipient scraping, contact harvesting,
automated outreach without consent, deceptive sender identity, evasion of
platform sending limits, or attempts to bypass unsubscribe/compliance controls.

### Hidden purchases or payments

Block purchases, payments, subscriptions, donations, bids, financial transfers,
trades, paid upgrades, ad spend, or billing changes unless the user sees the
amount, recipient/vendor, account, recurring terms, and explicitly approves the
transaction immediately before execution.

### Stealth data exfiltration

Block hidden, deceptive, or unapproved transfer of files, screenshots,
clipboard data, browser data, repository contents, private messages, contacts,
secrets, telemetry, or personal data to external destinations. Approved exports
must show destination, data categories, volume estimate, and retention risk.

## Policy-engine readiness checklist

Future implementation should provide:

- A profile resolver that combines user selection, workspace policy, connector
  policy, runtime trust, and action risk into an effective decision.
- A deny-by-default classifier for unknown actions and unknown targets.
- A risk-flag taxonomy matching the action envelope in this document.
- Approval prompts that include target, account, scope, reversibility, preview,
  and audit destination.
- Append-only audit records with secret redaction and correlation ids.
- Local-control checks for armed state, kill switch, dedicated browser profile,
  localhost-only control channels, bounded screenshots, and IPC-safe payloads.
- Schedule registration with owner, scope, stop condition, next run, retry cap,
  and policy version.
- Test fixtures for each profile, each hard stop, and each risk flag.
