# Explicit launch (operator commit path)

In Ham, **explicit launch** means a **committed** control-plane launch that goes through the **preview → verify → human-confirmed** operator flow **with** a cryptographic **`proposal_digest`**, a stable **`base_revision`**, and a **separate HAM operator secret** on the final step. Ham only calls the provider after those checks pass, then writes a durable **`ControlPlaneRun`** (and append-only audit where configured).

| Harness | Preview intent | Launch intent | HAM commit gate (examples) |
|--------|----------------|---------------|----------------------------|
| **Cursor Cloud Agent** | `cursor_agent_preview` | `cursor_agent_launch` | Digest + revision match; **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`** (or Clerk **`ham:launch`** when Clerk is enabled) — separate from **`CURSOR_API_KEY`** |
| **Factory Droid** | `droid_preview` | `droid_launch` | Digest + registry revision match; mutating tiers may require **`HAM_DROID_EXEC_TOKEN`** |

This path is what [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) calls the **operator** contract: bounded, reviewable, and aligned with [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) (record created **after** the commit boundary, not for preview alone).

## What explicit launch is *not*

**Direct HTTP proxies** under **`/api/cursor/...`** (for example **`POST /api/cursor/agents/launch`**) can start or follow a Cursor agent **without** the same digest + operator-bearer pipeline. Those surfaces are **valid** for dashboard or automation use cases but are **not** interchangeable with explicit launch for policy or audit semantics. See the “second path” note in [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) §3 and the launch row in [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) §1.

**Chat-only narration** does not launch anything: `POST /api/chat` maps intent to operator phases; the UI (or client) must send the structured **`operator`** payload with **`confirmed=true`** and matching preview fields when performing a real launch.

## Where it is implemented (pointers)

- Operator routing: [`src/ham/chat_operator.py`](../src/ham/chat_operator.py)
- Cursor preview/digest/launch: [`src/ham/cursor_agent_workflow.py`](../src/ham/cursor_agent_workflow.py)
- Product-facing operator table: [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) — “Operational chat”
