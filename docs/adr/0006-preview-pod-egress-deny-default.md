# 0006 — Preview pod egress: deny-default with curated allowlist

Tier 1 #6 in the Manus parity roadmap calls out preview pod unrestricted egress as HAM's biggest production security gap: gVisor sandboxing is in place, but pods can reach any external IP — exfiltrate workspace contents, mine, or pivot to internal services. We default the NetworkPolicy applied to preview pods to **deny-all-egress**, with a small curated allowlist for the hosts builders genuinely need.

## Initial allowlist (Phase 1 ships this; grows by tracked PR review)

| Purpose | Host pattern | Why |
|---|---|---|
| DNS resolution | UDP/53 to kube-dns | Required for any other rule to resolve names |
| npm registry | `registry.npmjs.org` | Generated builds run `npm install` |
| PyPI | `pypi.org`, `files.pythonhosted.org` | Generated Python builds run `pip install` |
| Google APIs | `*.googleapis.com` | GCS (snapshot reads), Firestore (event log), Cloud Run metadata |

The allowlist deliberately does **not** include LLM provider endpoints (Anthropic, OpenAI, OpenRouter, Hermes gateway). Preview pods do not call LLMs directly — the Worker does, and the Worker runs outside the preview pod. If a future architecture moves LLM calls into the pod (it shouldn't), the allowlist would need expansion through a separate ADR.

## Why deny-default

The Tier 1 framing is "biggest security gap." An allow-default policy with a denylist invites omission errors: any host you forgot to deny is reachable. Deny-default inverts the failure mode — a forgotten allow shows up as a builder breakage, which is loud and immediate. Loud-failure > silent-egress.

## Consequences

- The Worker that drives the pod must inject allowlist-aware fallbacks for any package it can't reach (or fail-loud with `package_install_denied` per the Contract 5 error catalog)
- Adding a domain to the allowlist requires a tracked PR that touches the NetworkPolicy YAML and references this ADR — that PR is the audit log
- Removing a domain from the allowlist is cheap (revert the PR); adding one after a breach is too late
- Builders that legitimately need other hosts (e.g. fetching a font from Google Fonts, hitting an analytics endpoint) will fail-loud on first attempt; product decision per case
- The roadmap's Tier 1 #15 (npm/pip allowlist) is a separate layer above this: package-level allowlist defends against malicious packages; host-level NetworkPolicy defends against malicious code in legitimate packages
