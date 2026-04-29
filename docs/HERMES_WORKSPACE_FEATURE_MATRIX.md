# Hermes Workspace Feature Matrix for HAM

## Purpose

This document maps Hermes Workspace-inspired features into HAM implementation phases without breaking HAM architecture boundaries.

HAM remains a managed AI operator console with a server-mediated contract:

- Browser calls HAM FastAPI only.
- Browser must not call upstream Hermes gateway URLs or keys directly.
- Normal chat path is browser -> HAM FastAPI -> Hermes HTTP gateway adapter.
- Cloud Agent launch/status is separate from normal Hermes chat.

## Locked Surfaces To Preserve

- `/chat`
- `/command-center`
- `/activity`
- `/skills`
- `/agents`
- `/runs`
- `/settings`

Any experimental or imported UI surface should live under a namespace such as `/hermes-lab/*`.

## Feature Matrix

| Feature | Category | User value | HAM equivalent today | Frontend-only? | Backend required? | Storage/schema required? | Auth/RBAC required? | Streaming contract impact? | Security review required? | Recommended phase | Implementation path | Notes / risks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Copy message action | Chat UX polish | Quickly reuse model output | Chat transcript view supports copyable text patterns | Yes | No | No | No | No | No | Phase 1 | Add per-message copy control in HAM chat message row | Low risk; no contract change |
| Clear composer action | Chat UX polish | Reset draft quickly | Existing composer input control | Yes | No | No | No | No | No | Phase 1 | Add explicit clear button near composer controls | No persistence impact |
| Streaming cursor indicator | Chat UX polish | Better live-response feedback | Chat stream already renders incremental updates | Yes | No | No | No | Yes (render-only) | No | Phase 1 | Add visual cursor tied to active stream state | Do not alter NDJSON semantics |
| Message timestamps | Chat UX polish | Better chronology and auditability | Activity and run timelines already time-based | Yes | No | Optional | No | No | No | Phase 1 | Render timestamp metadata in message UI | Use existing created-at fields only |
| Toast confirmations | UX feedback | Immediate success/error acknowledgment | Existing notification primitives in frontend | Yes | No | No | No | No | No | Phase 1 | Add lightweight toast for copy, save, rename | Keep copy concise and non-blocking |
| Session rename (basic) | Chat session management | Better organization of conversations | Session concepts exist in chat stream context | No | Yes | Yes | Optional | No | No | Phase 1 if session persistence exists; else Phase 2 | Expose rename endpoint for existing persisted sessions only | Frontend-only rename is misleading if not persisted |
| Read-only model/status indicator | Trust/observability | Clarifies selected provider/mode | Gateway mode and fallback status available server-side | No | Yes | No | Optional admin visibility | No | No | Phase 1 | Add read-only status payload in chat metadata response | Do not expose secrets or raw gateway URLs |
| Prompt library | Productivity | Reuse high-value prompts | No first-class prompt library route today | No | Yes | Yes | Yes | No | Moderate | Phase 2 | Introduce backend CRUD + scoped frontend picker | Needs ownership model and migration plan |
| Command palette | Navigation/productivity | Faster action discovery | HAM already has multiple routed surfaces | Mostly | Optional | Optional | Optional | No | Low | Phase 2 | Frontend command registry; backend hooks only for stateful actions | Keep actions limited to supported routes |
| Session search/archive/pin | Knowledge management | Find and retain important sessions | Runs/activity already list artifacts, not full chat archive features | No | Yes | Yes | Yes | No | Moderate | Phase 2 | Add backend index/filter endpoints + metadata updates | Requires clear retention policy |
| File attachments in chat | Rich context input | Submit files with prompts | Not available in current chat contract | No | Yes | Yes | Yes | Potentially | Yes | Phase 2 | Design backend upload scanning, storage, and reference model before UI | Treat as backend/security initiative, not UI-only |
| Admin-gated model selector (allowlisted) | Controlled flexibility | Let admins choose approved models | Gateway fallback and model handling exist server-side | No | Yes | Optional | Yes (admin) | Yes | Yes | Phase 2 | Server-maintained allowlist + admin UI; enforce server-side | Never expose unrestricted model IDs from browser |
| Execution Trace / Plan Block | Explainability | Shows actionable execution summary without hidden reasoning | Activity/runs expose operational progress | No | Yes | Optional | Optional | Yes | Moderate | Phase 2 | Add explicit structured trace block in stream/events contract | Must not request or reveal hidden chain-of-thought |
| Agent cards | Agent workspace UX | Quick status and access for agents | `/agents` exists with profile-aware context | Mostly | Yes | Optional | Yes | No | Moderate | Phase 3 | Extend `/agents` UI cards with runtime status data | Align with current HAM agent profile model |
| Cloud Agent activity feed | Agent operations | Real-time visibility into launches and progress | `/activity` and control-plane run APIs exist | No | Yes | Yes | Yes | Optional | Moderate | Phase 3 | Expand activity feed from control-plane run records | Preserve distinction from normal chat stream |
| Agent progress indicators | Agent operations | Understand current run stage quickly | Existing run and activity data model | Mostly | Yes | Optional | Yes | Optional | Moderate | Phase 3 | Add progress metadata rendering and polling/stream updates | Needs consistent stage taxonomy |
| Safe cancel/kill controls (bounded) | Operations control | Stop bad or stale runs safely | Depends on backend support and policy | No | Yes | Optional | Yes (admin/operator) | Optional | Yes | Phase 3 only if backend supports | Add server-enforced cancel endpoint and audited UI action | Never expose unrestricted kill/spawn |
| Read-only swarm view | Supervisor observability | Understand multi-agent state at a glance | Partial visibility through runs/activity | Mostly | Yes | Optional | Yes | Optional | Moderate | Phase 3 | Introduce read-only aggregate API and dashboard panel | Start read-only before any control actions |
| xterm.js terminal integration | Terminal surface | Embedded shell control | No approved terminal UI contract in HAM | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer until explicit security design and approvals | High-risk execution surface |
| Split terminal panes | Terminal surface | Parallel terminal workflows | None | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer with xterm baseline security package | Increases complexity and abuse surface |
| Terminal paste support | Terminal surface | Faster command input | None | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer pending command filtering/policy controls | Clipboard injection risk |
| Terminal tabs | Terminal surface | Multi-session shell workflows | None | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer pending session isolation model | Session confusion and privilege risk |
| hermes-proxy browser-routable surface | Gateway/proxy | Route traffic through browser-managed proxy | Violates HAM server mediation boundary | No | Yes | Yes | Yes | Yes | Yes (critical) | HOLD | Keep gateway routing server-side in HAM API only | Browser-side routing breaks architecture guarantees |
| workspace-daemon integration | Local process bridge | Background workspace automation | Not part of current HAM web contract | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer pending threat model and ops controls | Expands process and host-privilege surface |
| Browser-side gateway routing | Transport | Direct external gateway access from frontend | Explicitly disallowed by HAM contract | No | N/A | N/A | Yes | Yes | Yes (critical) | HOLD | Do not implement | Would expose keys/topology and bypass policy |
| Process launch controls from UI | Execution control | Start arbitrary local/remote processes | Not supported in HAM web UI | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer until allowlisted execution policy exists | High abuse potential |
| Arbitrary file-system access from UI | File operations | Direct workspace manipulation | Not supported in HAM browser contract | No | Yes | Yes | Yes | No | Yes (critical) | HOLD | Defer until strict sandbox + policy + audit exists | Data exfiltration and destructive risk |
| Arbitrary model selection | Model governance | Free model choice | Contradicts allowlist governance | No | Yes | Optional | Yes | Yes | Yes (critical) | HOLD | Replace with admin-only allowlisted selector | Cost, safety, and compliance risk |
| Unrestricted spawn/kill agent controls | Agent control plane | Full run orchestration from UI | Contradicts safe bounded control model | No | Yes | Yes | Yes | Optional | Yes (critical) | HOLD | Keep behind audited server policy and role checks | Operational blast-radius risk |

## Phase Totals

- Phase 1: 7 features
- Phase 2: 7 features
- Phase 3: 5 features
- HOLD: 11 features
- Total listed: 30 features

## Recommended Phase 1 Sequence

1. Add copy message and clear composer controls.
2. Add streaming cursor indicator and toast confirmations.
3. Add message timestamps using existing metadata fields.
4. Add read-only model/status indicator via server-provided metadata.
5. Add session rename only when persistence backend contract is confirmed.

## Explicit Corrections Applied

- Terminal, xterm, process, hermes-proxy, and workspace-daemon features are marked `HOLD`.
- File attachments are classified as backend + security work.
- Model selector is classified as admin-gated with server allowlist enforcement.
- "Thinking Block" is replaced with "Execution Trace / Plan Block."
- The matrix does not recommend copying the full Hermes Workspace app into HAM.
- Totals reflect the actual listed rows; no inflated feature counts.
