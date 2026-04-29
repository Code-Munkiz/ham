# Live Browser Copilot v1 (Desktop Local Control)

Live Browser Copilot v1 provides bounded browser interaction primitives over the trusted local GOHAM bridge in HAM Desktop.

This slice is **browser-only local control**. It does not provide machine execution, credential storage, coordinate clicking, or hidden destructive actions.

## Supported primitives

The trusted local bridge accepts only these actions:

- `navigate_and_capture`
- `observe`
- `click_candidate`
- `scroll`
- `type_into_field`
- `key_press`
- `wait`

## Browser intent payload shapes

All requests are sent through `webBridge.browserIntent(...)`.

### `navigate_and_capture`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "navigate_and_capture",
  "url": "https://example.com",
  "client_context": { "source": "desktop_goham" }
}
```

### `observe`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "observe",
  "client_context": { "source": "desktop_goham" }
}
```

Response includes compact page data and candidate-bounded clickable list (no DOM dump).

### `click_candidate`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "click_candidate",
  "candidate_id": "ham_cand_<epoch>_<n>",
  "client_context": { "source": "desktop_goham" }
}
```

### `scroll`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "scroll",
  "delta_y": 420,
  "client_context": { "source": "desktop_goham" }
}
```

### `type_into_field`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "type_into_field",
  "selector": "input[type=\"search\"]",
  "text": "antman 3",
  "clear_first": true,
  "client_context": { "source": "desktop_goham" }
}
```

### `key_press`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "key_press",
  "key": "Escape",
  "client_context": { "source": "desktop_goham" }
}
```

### `wait`

```json
{
  "intent_id": "desktop-goham-<ts>",
  "action": "wait",
  "wait_ms": 2000,
  "client_context": { "source": "desktop_goham" }
}
```

## Safety gates and blocked patterns

## Transport and trust

- Trusted token is validated in main/bridge, not renderer.
- Renderer has no token access.
- No generic IPC invoke path is exposed.

## Click model (candidate-bounded only)

- Clicks must reference a previously enumerated candidate id.
- Candidate ids are short-lived and scoped to a recent observe cycle.
- Coordinate clicking is not available in Copilot v1.

## Typing restrictions

- Typing only targets safe visible editable fields.
- Password and submit-like contexts are blocked.
- Risk labels/targets including terms like `pay`, `checkout`, `purchase`, `delete`, `sign in`, `log in`, and `password` are blocked.
- Typing payload is length-bounded.

## Key allowlist

Allowed keys:

- `Tab`
- `Escape`
- `ArrowUp`
- `ArrowDown`
- `ArrowLeft`
- `ArrowRight`
- `PageUp`
- `PageDown`
- `Home`
- `End`

Any other key is rejected with `key_not_allowed`.

## Wait bounds

- Wait must be bounded and short (0.5s to 3.0s).
- Unbounded/long waits are rejected.

## Inspector and audit expectations

- Workspace inspector records concise local-routing events and blocked reasons.
- Local control audit stream records bridge and local-control actions with redacted payloads.
- No credential/token fields are surfaced in renderer text.

## Known limitations

- No machine execution mode.
- No coordinate actions.
- No hidden submit/send/purchase/delete actions.
- No credential storage or login automation.
- Observe is compact and intentionally not a full debug DOM dump.

## Manual smoke checklist

1. Connect GOHAM in Desktop chat.
2. Confirm active local managed browser session.
3. Validate:
   - `what do you see?` (`observe`)
   - `scroll down` (`scroll`)
   - `click the first result` (`click_candidate`)
   - `type antman 3 into the search box` (`type_into_field`)
   - `press escape` (`key_press`)
   - `wait 2 seconds` (`wait`)
4. Validate blocked behavior:
   - password/hidden fields
   - submit-like controls
   - purchase/delete/login-risk labels
   - non-allowlisted keys
   - oversized typing payloads

