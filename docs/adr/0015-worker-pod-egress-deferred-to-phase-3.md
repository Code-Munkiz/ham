# 0015 — Worker pod egress: no NetworkPolicy in Phase 2.5; deferred to Phase 3

ADR-0006 locked a deny-default NetworkPolicy for preview pods because preview pods run user-generated code (the threat is the code itself). Worker pods run HAM-controlled code that needs to reach Firestore, Cloud Tasks, GCS, and LLM provider endpoints to execute Steps. The threat model is different; the egress shape is different. **Phase 2.5 ships Worker pods with no NetworkPolicy.** This is a temporary posture documented here so it isn't forgotten.

## Why not NetworkPolicy now

- LLM provider IPs (OpenRouter, Anthropic, OpenAI) are not stable. Kubernetes NetworkPolicy is L3/L4 — no native FQDN allowlist. Pinning by IP CIDR would either drift constantly or be too broad to be useful.
- The Worker's egress surface is large and code-driven (each new model integration adds a destination). Maintaining a hand-curated allowlist would either lag behind code changes or be permissive enough to add no value.
- Doing this right needs an egress proxy or service mesh with FQDN policy. That's a Phase 3 hardening pass, not a Tier 1 close-out.

## What we ship instead (defence-in-depth, no NetworkPolicy)

These are the guardrails the pod spec enforces:

- **Separate namespace** from preview pods. Worker pods land in their own namespace so future NetworkPolicy work has a clean blast radius.
- **Workload Identity, no static secrets.** No JSON keys, no long-lived tokens, no Secret volume mounts. If a Worker is compromised, the attacker inherits Firestore datastore-user scope and nothing else.
- **No `privileged`, no `hostPath`, no `hostNetwork`, no broad capabilities.** Standard pod hardening defaults.
- **Log provider class only.** No URLs with credentials, no Authorization headers, no JWT tokens in logs.
- **`automountServiceAccountToken: true`** stays on (needed for Workload Identity), but the KSA has namespace-scoped Firestore-only RBAC via the bound GSA.

## What changes in Phase 3

- ADR for egress posture: choose between (a) NetworkPolicy with broad CIDR allowlist + per-provider documentation, (b) egress proxy (e.g., a sidecar HTTP proxy with FQDN allowlist), or (c) service mesh (Cilium / Istio with L7 policy).
- Once a posture is chosen, apply the matching policy to the Worker namespace.
- Until then, this ADR is the standing answer to "why does the Worker pod have no NetworkPolicy".

## Consequences

- Worker pods can reach any external endpoint, including arbitrary IPs. The threat is mitigated by Worker code being HAM-controlled, not by network policy.
- A bug in HAM code that exfiltrates data would not be blocked at the network layer; it would be caught (if at all) by code review or audit logging.
- The Phase 3 hardening work is a known follow-up; this ADR exists so it shows up in any future "what's the security posture of the Worker pod" question.
