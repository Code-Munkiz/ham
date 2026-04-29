<!-- Phase 0 contract only. No runtime implementation in this document. -->

# HAM Web App -> Local Windows Runtime Bridge MVP

Status: Phase 0 (contract/docs only)  
Scope: Security and API contract for web-to-local control bridge  
Non-goal: No endpoint/listener/runtime implementation in this phase

## Product Goal

HAM must support both mandatory lanes with the same local execution target (the end user's Windows machine):

1. HAM Web App
   - Pairs with a trusted local Windows runtime.
   - Requests local browser-real control first.
   - Requests local machine escalation only when allowed.
2. HAM Desktop / IDE App
   - Includes, launches, or connects to the same local runtime.
   - Uses the same local-control safety gates and escalation policy.

Cloud Run or VM browser runtime may support hosted workflows and metadata validation, but is not the primary end-user control plane for local computer control.

## Recommended Architecture

Decision: hybrid

- Reuse existing web/local-runtime discovery UX where possible (`/api/workspace/health` and local runtime URL handling).
- Add a separate localhost-only local-control bridge for browser-real and machine escalation commands.
- Keep Files/Terminal local API and local-control bridge API separate.
- Preserve Desktop runtime authority for:
  - kill switch
  - armed local-control requirements
  - browser-real permission gating
  - URL policy enforcement
  - dedicated profile and localhost CDP safety
  - screenshot bounds and audit

## Existing Reuse Boundaries

- Reuse: web-side local runtime discovery and connection UX.
- Do not reuse for control commands: current Files/Terminal endpoints are not the local-control command channel.
- Local-control command handling remains a desktop-runtime responsibility, not a cloud API path.

## Bridge Namespace and Transport

Namespace:

- `http://127.0.0.1:<bridge_port>/ham/local-control/v1/*`

MVP transport constraints:

- Bind only to `127.0.0.1`.
- Do not bind to `0.0.0.0`.
- Deny `::1` in MVP unless explicitly added with separate review.
- No cookies. Bearer token only.
- Deny-by-default on all command endpoints.

## Origin Policy

Allowed canonical web origin:

- `https://ham-nine-mu.vercel.app`

Explicitly denied stale origins:

- `https://ham-kappa-fawn.vercel.app`
- `https://aaron-bundys-projects.vercel.app`

Notes:

- Browser `Origin` checks are mandatory but not sufficient.
- Non-browser clients can spoof `Origin`; pairing token and runtime arming are also required.

## Endpoint Contract

### 1) GET `/health`

Purpose:

- Minimal unauthenticated bridge liveness and protocol signal.

Auth:

- No bearer token required.

Required headers:

- `Origin` (must be canonical for browser callers)

Response (minimal only):

```json
{
  "ok": true,
  "bridge_version": "v1",
  "pairing_required": true
}
```

Failure reason codes:

- `origin_not_allowed`
- `bridge_unavailable`

Audit fields:

- `event=bridge_health_read`
- `origin`
- `remote_addr`
- `timestamp`

Safety gates checked:

- origin allowlist
- listener bound to loopback

### 2) POST `/pairing/exchange`

Purpose:

- Exchange one-time pairing code from local runtime UI for short-lived bearer token.

Auth:

- No existing bearer required.

Required headers:

- `Origin`
- `Content-Type: application/json`

Request body:

```json
{
  "pairing_code": "123-456",
  "client_nonce": "uuid",
  "requested_origin": "https://ham-nine-mu.vercel.app"
}
```

Response:

```json
{
  "ok": true,
  "token_type": "Bearer",
  "access_token": "opaque_token",
  "expires_in_sec": 900,
  "session_id": "pair_sess_abc",
  "scopes": [
    "status.read",
    "browser.intent",
    "machine.escalation.request"
  ]
}
```

Failure reason codes:

- `pairing_disabled`
- `origin_not_allowed`
- `pairing_code_invalid`
- `pairing_code_expired`
- `pairing_code_already_used`

Audit fields:

- `event=pairing_exchange`
- `session_id`
- `origin`
- `client_nonce`
- `result`
- `reason_code`
- `timestamp`

Safety gates checked:

- local runtime is armed for pairing
- one-time code validity (TTL + single use)
- origin allowlist match

### 3) POST `/pairing/revoke`

Purpose:

- Revoke current session token; optionally all sessions from trusted local UI.

Auth:

- Bearer token required for session revoke.
- Local desktop UI may trigger global revoke without web token.

Required headers:

- `Authorization: Bearer <token>`
- `Origin`

Request body:

```json
{
  "scope": "session",
  "reason": "user_requested"
}
```

Response:

```json
{
  "ok": true
}
```

Failure reason codes:

- `token_invalid`
- `token_expired`
- `origin_not_allowed`

Audit fields:

- `event=pairing_revoke`
- `scope`
- `session_id`
- `origin`
- `timestamp`

Safety gates checked:

- token validity
- origin binding

### 4) GET `/status`

Purpose:

- Return sanitized local-control status for web UI decisions.

Auth:

- Bearer token required.

Required headers:

- `Authorization`
- `Origin`

Response (sanitized):

```json
{
  "ok": true,
  "supported_platform": true,
  "kill_switch_engaged": false,
  "browser_real": {
    "supported": true,
    "armed": true,
    "gate_blocked_reason": null,
    "managed_profile": true,
    "cdp_localhost_only": true
  }
}
```

Failure reason codes:

- `token_invalid`
- `token_expired`
- `origin_not_allowed`

Audit fields:

- `event=status_read`
- `session_id`
- `origin`
- `timestamp`

Safety gates checked:

- token + origin validation
- response redaction (no raw local paths/profile dirs)

### 5) POST `/browser/intent`

Purpose:

- Route browser intent to desktop local-control browser-real path.

Auth:

- Bearer token required.

Required headers:

- `Authorization`
- `Origin`
- `Content-Type: application/json`

Request body:

```json
{
  "intent_id": "uuid",
  "action": "navigate_and_capture",
  "url": "https://example.com",
  "allow_loopback": false
}
```

Response:

```json
{
  "ok": true,
  "status": "executed",
  "browser_bridge": {
    "status": "executed",
    "summary": "navigated_and_captured",
    "step_count": 2
  }
}
```

Failure reason codes:

- `token_invalid`
- `origin_not_allowed`
- `kill_switch_engaged`
- `real_browser_not_armed`
- `real_browser_permission_off`
- `chromium_not_found`
- `url_policy_blocked`
- `browser_runtime_error`

Audit fields:

- `event=browser_intent`
- `intent_id`
- `origin`
- `session_id`
- `result`
- `reason_code`
- `timestamp`

Safety gates checked:

- kill switch
- armed requirement
- browser-real permission
- executable discovery
- URL policy
- dedicated profile usage
- localhost-only CDP
- screenshot bounds

### 6) POST `/machine/escalation-request`

Purpose:

- Request narrow browser-to-machine escalation when policy allows.

Auth:

- Bearer token required.

Required headers:

- `Authorization`
- `Origin`
- `Content-Type: application/json`

Request body:

```json
{
  "intent_id": "uuid",
  "trigger": "partial",
  "user_confirmed": true,
  "requested_scope": "narrow_task"
}
```

Response:

```json
{
  "ok": true,
  "selected_mode": "machine",
  "escalated_from": "browser",
  "escalation_trigger": "partial"
}
```

Failure reason codes:

- `token_invalid`
- `origin_not_allowed`
- `kill_switch_engaged`
- `escalation_not_allowed`
- `explicit_user_approval_required`
- `machine_permission_off`

Audit fields:

- `event=machine_escalation_request`
- `intent_id`
- `trigger`
- `approved`
- `origin`
- `session_id`
- `result`
- `reason_code`
- `timestamp`

Safety gates checked:

- token + origin
- explicit user approval
- local runtime policy and permissions
- deny-by-default escalation guard

## Pairing and Token Model

- Pairing must be initiated from trusted local runtime UI.
- One-time pairing code:
  - suggested TTL: 120 seconds
  - single use
- Access token:
  - required on every command endpoint
  - origin/session-bound
  - suggested TTL: 15 minutes
- Storage on web side:
  - memory-first
  - `sessionStorage` fallback allowed for MVP (higher risk)
  - never `localStorage`
- Revoke behaviors:
  - revoke current session (web)
  - revoke all sessions (desktop runtime authority)
- Default behavior:
  - deny when missing token, expired token, bad origin, or unarmed runtime

## Browser-Real Handoff Rules

Any bridge-driven browser action must preserve existing desktop local-control invariants:

- kill switch enforced
- armed local-control requirement
- browser-real permission requirement
- executable discovery check
- URL policy from `desktop/local_control_browser_url.cjs`
- dedicated HAM browser profile
- localhost-only CDP
- bounded screenshot output
- never use default browser profile
- never expose raw profile path in payloads

## Browser -> Machine Escalation Rules

Escalation may be allowed only when:

- browser-real returns partial
- browser-real is insufficient for local desktop/app boundary
- user explicitly approves
- local runtime policy gates allow escalation

Escalation must be denied when:

- token/origin invalid
- kill switch engaged
- no explicit user/local runtime approval
- request implies arbitrary OS control outside narrow approved scope

Phase boundary:

- Phase 3 implements browser-real handoff only.
- Machine escalation remains Phase 4 and must not be silently introduced in Phase 3.

## Threat Model (MVP)

### Threats

- malicious website targeting localhost
- forged `Origin` from non-browser clients
- stale token reuse
- token leakage
- CSRF/local network abuse
- command replay
- broad command injection
- raw local path/profile leakage
- privilege escalation
- hosted/cloud context attempting local control
- localhost port scanning

### Mitigations

- loopback binding to `127.0.0.1` only
- strict origin allowlist to canonical frontend
- one-time pairing code + short-lived bearer
- token bound to origin/session, revocable
- nonce and replay rejection for mutating requests
- narrow endpoint surface and typed request schema
- deny-by-default policy checks at every command
- sanitized responses and audit redaction
- no cookies, no unauth command endpoints

## Implementation Phases

### Phase 0: Contract/docs only

- Likely files:
  - `docs/desktop/local_web_bridge_mvp.md`
- Tests required:
  - none
- Acceptance:
  - contract approved with security gates and endpoint semantics
- Rollback:
  - revert docs file

### Phase 1: Bridge health + pairing skeleton

- Likely files:
  - `desktop/main.cjs`
  - `desktop/local_control_policy.cjs`
  - `desktop/local_control_audit.cjs`
  - desktop tests for pairing/origin/token checks
- Tests required:
  - origin allow/deny
  - code TTL/single-use
  - token TTL/revoke
- Acceptance:
  - minimal bridge liveness + pairing flow working under deny-by-default
- Rollback:
  - bridge disabled behind feature flag; desktop lane unaffected

### Phase 2: Web discovery/status integration

- Likely files:
  - `frontend/src/features/hermes-workspace/adapters/localRuntime.ts`
  - `frontend/src/features/hermes-workspace/components/LocalMachineConnectCta.tsx`
  - settings UI status components
- Tests required:
  - discovery and paired-status handling
- Acceptance:
  - web app can detect and display paired bridge status
- Rollback:
  - hide paired bridge path, keep Files/Terminal discovery behavior

### Phase 3: Browser-real handoff

- Likely files:
  - desktop bridge handlers in `desktop/main.cjs`
  - frontend bridge adapter for browser intent
- Tests required:
  - gate preservation and URL policy enforcement
  - screenshot bounds and redaction checks
- Acceptance:
  - web intent can invoke local browser-real via existing desktop gates
- Rollback:
  - disable browser intent endpoint; keep status/pairing

### Phase 4: Narrow browser -> machine escalation

- Likely files:
  - desktop escalation handlers
  - web execution-mode/escalation UI logic
- Tests required:
  - explicit approval requirement
  - kill-switch and permission denial paths
- Acceptance:
  - escalation allowed only for approved narrow cases
- Rollback:
  - disable escalation endpoint, keep browser handoff path

### Phase 5: Audit/telemetry hardening

- Likely files:
  - desktop audit modules
  - docs for audit schema
- Tests required:
  - replay, redaction, reason-code coverage
- Acceptance:
  - complete auditable trail without sensitive leakage
- Rollback:
  - revert hardening deltas while preserving baseline audit

## Guardrails

- Do not implement runtime code in Phase 0.
- Do not add listeners or endpoints in Phase 0.
- Do not change Cloud Run/Vercel behavior.
- Do not weaken existing local-control safety gates.

