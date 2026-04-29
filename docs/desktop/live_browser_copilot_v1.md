# Live Browser Copilot v1 (Local Browser Control Contract)

Status: draft contract for implementation planning.  
Implementation status: not implemented in runtime code by this document.

## 1) Scope

This contract defines a local, HAM-managed browser copilot API with the following actions only:

- `observe`
- `click_candidate`
- `scroll`
- `type_into_field`
- `key_press`
- `wait`
- session controls: `pause`, `takeover`, `resume`, `stop`

Out of scope for v1:

- Arbitrary coordinate clicking (no `x/y` action contract).
- DOM-wide unrestricted action execution.
- Background autonomous purchases, submits, destructive actions, or credential submission.

## 2) Core Safety Requirements (Normative)

1. Candidate-bounded clicks only:
   - Every click MUST target a previously returned `candidate_id` from `observe`.
   - Candidate IDs are short-lived and bound to an observation generation.
2. No arbitrary coordinates:
   - API MUST reject coordinate click requests with `reason_code=arbitrary_coordinates_forbidden`.
3. No hidden submit/send/purchase/delete:
   - Copilot MUST block clicks on hidden or ambiguous high-risk intent elements.
   - Copilot MUST block high-risk actions unless user takeover is active.
4. Login handoff to user:
   - Copilot MUST request takeover before entering credentials, pressing login/continue buttons, or handling MFA prompts.
5. Isolated HAM profile:
   - Sessions MUST use a HAM-isolated browser profile directory separate from normal user profile/cookies.
6. Audit events:
   - Every request MUST emit a structured audit event with outcome and reason code.
7. Concise chat responses:
   - User-facing response text MUST be short and operational (target <= 240 chars, max 2 lines).
8. Inspector/debug details:
   - Detailed action diagnostics MUST be returned in a separate inspector payload, not mixed into concise chat text.

## 3) Session and Candidate Model

## 3.1 Session states

- `active`: copilot may execute bounded actions.
- `paused`: automation halted; observe optional, mutations blocked.
- `takeover`: user is controlling the session; copilot mutation actions blocked.
- `stopped`: terminal state; no further actions.

## 3.2 Candidate definition

An `observe` call returns clickable/typeable candidates with:

- `candidate_id`: opaque ID (unique within session + generation).
- `generation_id`: observe generation token (monotonic).
- `kind`: `clickable | typeable | scroll_region | form_submit | nav | other`
- `label`: visible text or accessibility label.
- `selector_hint`: stable diagnostic selector hint (not executable input contract).
- `bbox`: viewport-relative rectangle for inspector only.
- `visibility`: `visible | occluded | offscreen | hidden`.
- `risk_tags`: array such as `["submit", "delete", "purchase", "auth"]`.
- `expires_at`: timestamp for candidate validity.

`click_candidate` and `type_into_field` MUST include `generation_id` to prevent stale actions.

## 4) HTTP API Contract (v1)

Base prefix: `/api/browser/copilot`

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Create isolated copilot session |
| `GET` | `/sessions/{session_id}` | Session state snapshot |
| `POST` | `/sessions/{session_id}/observe` | Capture page state and candidates |
| `POST` | `/sessions/{session_id}/actions/click-candidate` | Click a candidate-bounded target |
| `POST` | `/sessions/{session_id}/actions/scroll` | Scroll viewport or region |
| `POST` | `/sessions/{session_id}/actions/type-into-field` | Type into a typeable candidate |
| `POST` | `/sessions/{session_id}/actions/key-press` | Press allowlisted keys |
| `POST` | `/sessions/{session_id}/actions/wait` | Wait for UI/network stabilization |
| `POST` | `/sessions/{session_id}/control/pause` | Pause automation |
| `POST` | `/sessions/{session_id}/control/takeover` | Transfer control to user |
| `POST` | `/sessions/{session_id}/control/resume` | Return control to copilot |
| `POST` | `/sessions/{session_id}/control/stop` | End session |
| `GET` | `/sessions/{session_id}/audit` | Fetch bounded audit trail |

## 4.1 Common request envelope

```json
{
  "owner_key": "local-dev",
  "request_id": "9f2f7ae5-49f2-4ef6-af7f-c4fcf2de4c9f",
  "debug": false
}
```

## 4.2 Common success envelope

```json
{
  "ok": true,
  "session_id": "brs_01J...",
  "state": "active",
  "chat": {
    "response": "Clicked “Open settings”.",
    "next_hint": "Use observe to refresh candidates."
  },
  "inspector": {
    "action_id": "act_01J...",
    "timings_ms": {
      "total": 142
    },
    "debug_notes": []
  }
}
```

## 4.3 Common error envelope

```json
{
  "ok": false,
  "session_id": "brs_01J...",
  "error": {
    "reason_code": "candidate_expired",
    "message": "Candidate is stale. Run observe again.",
    "retryable": true
  },
  "chat": {
    "response": "That target is stale. I need a fresh observe pass."
  },
  "inspector": {
    "action_id": "act_01J...",
    "debug_notes": [
      "generation_id mismatch: expected gen_44, got gen_42"
    ]
  }
}
```

## 5) Endpoint Shapes and Examples

## 5.1 Create session

`POST /api/browser/copilot/sessions`

Request:

```json
{
  "owner_key": "local-dev",
  "viewport": { "width": 1280, "height": 720 },
  "start_url": "https://example.com",
  "profile_mode": "ham_isolated"
}
```

Response:

```json
{
  "ok": true,
  "session_id": "brs_01J9XYZ",
  "state": "active",
  "profile": {
    "mode": "ham_isolated"
  }
}
```

## 5.2 Observe

`POST /api/browser/copilot/sessions/{session_id}/observe`

Request:

```json
{
  "owner_key": "local-dev",
  "include_screenshot": true,
  "max_candidates": 40,
  "debug": true
}
```

Response (truncated):

```json
{
  "ok": true,
  "session_id": "brs_01J9XYZ",
  "state": "active",
  "observe": {
    "generation_id": "gen_45",
    "url": "https://example.com/settings",
    "title": "Settings",
    "candidates": [
      {
        "candidate_id": "cand_001",
        "generation_id": "gen_45",
        "kind": "clickable",
        "label": "Profile",
        "visibility": "visible",
        "risk_tags": []
      },
      {
        "candidate_id": "cand_019",
        "generation_id": "gen_45",
        "kind": "form_submit",
        "label": "Delete account",
        "visibility": "visible",
        "risk_tags": ["delete", "submit"]
      }
    ]
  },
  "chat": {
    "response": "Found 21 candidates. High-risk actions are gated."
  },
  "inspector": {
    "action_id": "act_01JA",
    "candidate_count": 21
  }
}
```

## 5.3 Click candidate

`POST /api/browser/copilot/sessions/{session_id}/actions/click-candidate`

Request:

```json
{
  "owner_key": "local-dev",
  "generation_id": "gen_45",
  "candidate_id": "cand_001",
  "intent": "open_settings"
}
```

Response:

```json
{
  "ok": true,
  "session_id": "brs_01J9XYZ",
  "state": "active",
  "chat": {
    "response": "Clicked “Profile”."
  },
  "inspector": {
    "action_id": "act_01JB",
    "candidate_id": "cand_001"
  }
}
```

Blocked high-risk example:

```json
{
  "ok": false,
  "session_id": "brs_01J9XYZ",
  "error": {
    "reason_code": "hidden_critical_action_blocked",
    "message": "High-risk submit/delete action requires user takeover.",
    "retryable": false
  },
  "chat": {
    "response": "That action is high-risk. Please take over to continue."
  },
  "inspector": {
    "action_id": "act_01JC",
    "candidate_id": "cand_019",
    "risk_tags": ["delete", "submit"]
  }
}
```

## 5.4 Scroll

`POST /api/browser/copilot/sessions/{session_id}/actions/scroll`

```json
{
  "owner_key": "local-dev",
  "target": "viewport",
  "delta_x": 0,
  "delta_y": 650
}
```

## 5.5 Type into field

`POST /api/browser/copilot/sessions/{session_id}/actions/type-into-field`

```json
{
  "owner_key": "local-dev",
  "generation_id": "gen_45",
  "candidate_id": "cand_006",
  "text": "ham-demo",
  "clear_first": true
}
```

Notes:

- MUST fail if candidate is not `typeable`.
- MUST fail with `login_handoff_required` when field appears credential-sensitive.

## 5.6 Key press

`POST /api/browser/copilot/sessions/{session_id}/actions/key-press`

```json
{
  "owner_key": "local-dev",
  "key": "Enter"
}
```

Key policy:

- v1 allowlist should prefer navigation/edit keys (`Enter`, `Tab`, `Escape`, arrows, `Backspace`).
- Shortcut chords that trigger destructive/submit flows SHOULD be denied by default.

## 5.7 Wait

`POST /api/browser/copilot/sessions/{session_id}/actions/wait`

```json
{
  "owner_key": "local-dev",
  "wait_for": "network_idle",
  "timeout_ms": 4000
}
```

Allowed `wait_for`: `network_idle | dom_stable | selector_visible`.

## 5.8 Session control

Pause:

`POST /api/browser/copilot/sessions/{session_id}/control/pause`

```json
{
  "owner_key": "local-dev",
  "reason": "user_requested"
}
```

Takeover:

`POST /api/browser/copilot/sessions/{session_id}/control/takeover`

```json
{
  "owner_key": "local-dev",
  "reason": "login_handoff"
}
```

Resume:

`POST /api/browser/copilot/sessions/{session_id}/control/resume`

```json
{
  "owner_key": "local-dev",
  "confirm_safe": true
}
```

Stop:

`POST /api/browser/copilot/sessions/{session_id}/control/stop`

```json
{
  "owner_key": "local-dev",
  "reason": "task_complete"
}
```

## 6) Failure Reason Codes

| reason_code | Meaning | Typical HTTP |
|---|---|---|
| `invalid_request` | Schema/field validation failed | `400` |
| `session_not_found` | Unknown session | `404` |
| `session_owner_mismatch` | Wrong owner key | `403` |
| `session_paused` | Action disallowed while paused | `409` |
| `session_takeover_required` | User takeover required before action | `409` |
| `session_stopped` | Session is terminal | `409` |
| `candidate_not_found` | Candidate ID not present in generation | `422` |
| `candidate_expired` | Candidate stale or generation mismatch | `422` |
| `candidate_not_visible` | Candidate hidden/occluded/offscreen | `422` |
| `candidate_not_typeable` | Type action on non-typeable candidate | `422` |
| `arbitrary_coordinates_forbidden` | Coordinate click attempt rejected | `422` |
| `hidden_critical_action_blocked` | Hidden/high-risk action blocked | `422` |
| `login_handoff_required` | Credential or auth gate requires user control | `409` |
| `key_not_allowed` | Key/chord outside allowlist | `422` |
| `policy_blocked_url` | Domain/scheme blocked by policy | `422` |
| `rate_limited` | Per-session action limit exceeded | `429` |
| `runtime_unavailable` | Browser engine unavailable | `503` |
| `internal_error` | Unclassified runtime failure | `500` |

## 7) Audit Event Contract

Every endpoint call MUST append an audit event:

```json
{
  "event_id": "evt_01JF",
  "timestamp": "2026-04-29T05:10:42Z",
  "session_id": "brs_01J9XYZ",
  "owner_key_hash": "sha256:...",
  "action": "click_candidate",
  "request_id": "9f2f7ae5-49f2-4ef6-af7f-c4fcf2de4c9f",
  "outcome": "blocked",
  "reason_code": "hidden_critical_action_blocked",
  "candidate_id": "cand_019",
  "generation_id": "gen_45",
  "latency_ms": 47
}
```

Audit retrieval:

- `GET /api/browser/copilot/sessions/{session_id}/audit?limit=200&cursor=...`
- MUST support stable pagination.
- MUST redact sensitive typed text values in persisted payloads.

## 8) Chat vs Inspector Output Contract

- `chat.response`: concise operator-facing one-liner.
- `chat.next_hint`: optional concise follow-up suggestion.
- `inspector`: machine-debug details, timing, candidate metadata, policy traces.
- Debug verbosity enabled only when `debug=true` or equivalent privileged mode.

This split prevents noisy chat output while preserving deep diagnostics for operator UI/debug panels.

## 9) Tests Needed Before v1 GA

## 9.1 Unit tests

- Candidate generation IDs are monotonic and expire correctly.
- Click requires candidate + matching generation.
- Coordinate click payload rejected with `arbitrary_coordinates_forbidden`.
- High-risk hidden action classifier blocks submit/send/purchase/delete patterns.
- Login sensitivity detector returns `login_handoff_required`.
- Session state machine correctness (`active -> paused/takeover -> resume -> stopped`).

## 9.2 API tests

- Endpoint schema validation and error envelopes.
- Owner mismatch and auth failures.
- Reason-code-to-HTTP mapping.
- Audit event emission for success, blocked, and failure paths.
- Inspector payload present; chat text remains concise.

## 9.3 End-to-end tests

- Observe -> click_candidate happy path on safe UI target.
- Observe -> blocked delete/submit path requiring takeover.
- Login flow triggers takeover requirement and allows resume after user handoff.
- Pause/stop prevent further mutating actions.
- Isolated profile test: no cookie/session bleed across copilot sessions.

## 10) Rollout Sequence

1. Phase 0 (contract + flags):
   - Add contract doc and feature flag scaffold (`copilot_v1_local`).
2. Phase 1 (observe + audit, no mutating actions):
   - Ship `sessions`, `observe`, `audit` with inspector payload.
3. Phase 2 (bounded actions):
   - Enable `click_candidate`, `scroll`, `wait`, `key_press` with policy gates.
   - Explicitly disable coordinate action paths for copilot mode.
4. Phase 3 (typing + handoff controls):
   - Enable `type_into_field`, `pause/takeover/resume/stop`.
   - Enforce login handoff and high-risk action blocks.
5. Phase 4 (default-on for local copilot):
   - Enable by default in local environment, keep runtime kill switch.
   - Monitor audit reason-code distribution and false-positive rates.

## 11) Compatibility Notes

- Existing browser runtime routes may continue in parallel for non-copilot surfaces.
- `click-xy` remains out of scope for this copilot contract and MUST NOT be used by v1 copilot clients.
- This contract defines the safe local copilot behavior even when lower-level runtime primitives exist.
