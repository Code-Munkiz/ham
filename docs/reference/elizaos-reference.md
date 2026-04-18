# ElizaOS — reference summary

> Reference summary for future HAM adapter/context work. **Not** a source of shipped HAM truth. Concepts evolve upstream; verify against current ElizaOS docs when implementing.

## Character vs agent

- **Character** — Persona-facing definition: name, bio, lore, voice, and presentation. Often maps to a single “face” the user chats with.
- **Agent** — Runtime entity that loads a character (or template), connects model + plugins + memory, and handles turns. Multiple agents may share patterns; characters are the primary user-facing identity slice.

## Persona / identity

- Persona layers typically include style, tone, and behavioral constraints separate from raw model weights.
- Identity can be split across **system prompts**, **character files**, and **lore** so the same stack can swap personas without rewriting core runtime code.

## Plugins

- Plugin model usually covers: **actions** (things the agent can do), **providers** (data sources), **evaluators** (routing/heuristics), and **services** (cross-cutting helpers).
- Plugins extend capability without forking core; adapter work often maps HAM “tools” or “behaviors” to plugin-shaped surfaces.

## Model / provider settings

- Model choice is typically **per-agent** or **per-character**, with provider API keys and model IDs in config or secrets—not hardcoded in persona text.
- Temperature, max tokens, and similar knobs are usually first-class config, separate from persona prose.

## Secrets

- API keys and tokens are expected to live in **environment variables** or a **secrets manager** pattern—not committed in character JSON.

## Knowledge

- **Knowledge** plugins or **RAG** attachments let characters draw from documents, URLs, or vector stores without stuffing everything into the prompt.
- Distinct from **memory** (conversation-scoped recall) in many setups.

## Style / templates

- **Message templates** and **style guides** shape how the model formats output (markdown, brevity, code fences).
- Often separate from the character’s biographical “who” content.

## Config surface (typical)

- Character definition files (YAML/JSON/TS depending on version).
- Agent defaults: model ID, provider, plugin enablement.
- Environment: provider keys, logging, feature flags.

## HAM stance

HAM may **borrow patterns** (persona vs tool vs memory separation) without adopting ElizaOS config filenames or schemas. Any future adapter is a **projection**, not parity.
