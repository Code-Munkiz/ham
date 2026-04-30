# Social Persona

HAM Social uses a canonical persona so X, Telegram, Discord, and later
providers share one identity before any platform-specific adaptation is
applied.

## Canonical Persona

- `persona_id`: `ham-canonical`
- `version`: `1`
- `display_name`: `Ham`
- Source: `src/ham/social_persona/personas/ham-canonical.v1.yaml`

The persona defines mission, values, tone, vocabulary, humor and emoji rules,
platform adaptations, prohibited content, safety boundaries, and bounded
examples.

## Current State

SP-1 is read-only:

- The registry is committed as structured YAML.
- The API exposes bounded read-only DTOs under `/api/social/persona/current`
  and `/api/social/personas/ham-canonical`.
- The Social cockpit renders the canonical card, platform adaptations, voice
  examples, refusal examples, and a digest-protection placeholder.

SP-1 does not:

- Edit personas.
- Call models.
- Send provider messages.
- Start or stop Hermes gateway processes.
- Export Hermes or Eliza character files.

## Future Digest Use

Future Social preview payloads should include:

- `persona_id`
- `persona_version`
- `persona_digest`

Future apply routes should block if the current persona digest differs from
the preview digest.
