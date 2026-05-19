# 0009 — Planner uses the user's BYO OpenRouter key; regex fallback when no key

Phase 2 introduces a Planner LLM call that turns a builder-mutation chat turn into a **Plan** (Phase 0 schema). We had to decide whose key pays for the call. Manus / Replit / Base44 all use central provider keys and abstract model choice from the user — which conflicts with HAM's explicit BYO-keys position (see `PRODUCT_DIRECTION.md` and the Manus parity roadmap). We chose **the user's BYO OpenRouter key**, routed through the existing `complete_chat_messages_openrouter` path in `src/llm_client.py`. When no OpenRouter key is configured (`normalized_openrouter_api_key()` returns empty), the chat handler **falls back to today's regex `route_agent_intent` + `builder_mutation_router` flow** — no Plan, no approval gate, no Worker, just the legacy template-scaffold behavior the project shipped before Phase 2.

## Why BYO over central

BYO is HAM's product position. Adopting central-key Planner here would have introduced a new cost model (HAM-owned), a new billing surface, and an implicit contradiction with the rest of the chat (which already uses the user's key via `normalized_openrouter_api_key`). Reusing the same key keeps the cost story coherent: the user pays for their planning, the same way they pay for their replies.

## Why regex fallback instead of "block builder until a key is configured"

Blocking would force every new user to configure credentials before the builder works at all — high-friction onboarding, especially for the 3-5-user team-scope HAM targets. The regex fallback preserves today's behavior for the no-key case, so the builder degrades gracefully into "no Plans, no approval gate" rather than failing closed. The cost is a UX gap (no-key users miss out on the Planner feature), but the gap is one settings change away from being closed.

## Consequences

- The Planner is one more OpenRouter-billed call per builder-mutation chat turn — costs scale with the user, not HAM
- The model is picked the same way as chat (`HERMES_GATEWAY_MODEL` / `DEFAULT_MODEL`), with an optional `HAM_PLANNER_MODEL` env override if the user wants a different (typically faster/cheaper) model for planning specifically
- The Planner must tolerate malformed JSON output: one retry with a stricter system prompt, then emit an error and let the user re-prompt — no auto-fallback to a synthetic Plan
- The no-key fallback to regex is permanent; we are not deprecating `route_agent_intent` or `builder_mutation_router`
- If HAM ever pivots away from BYO (e.g. introduces a "free Planner tier"), reversing this ADR means rerouting the key source — the rest of the Planner architecture stays unchanged
