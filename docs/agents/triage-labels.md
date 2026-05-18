# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used on this repo's GitHub Issues.

| Label in mattpocock/skills | Label in our tracker     | Meaning                                  |
| -------------------------- | ------------------------ | ---------------------------------------- |
| `needs-triage`             | `status:needs-triage`    | Maintainer needs to evaluate this issue  |
| `needs-info`               | `status:needs-info`      | Waiting on reporter for more information |
| `ready-for-agent`          | `status:ready-for-agent` | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `status:ready-for-human` | Requires human implementation            |
| `wontfix`                  | `wontfix`                | Will not be actioned (GitHub default)    |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from the right-hand column.

## Status: three labels not yet created

`status:needs-triage` already exists (per `AGENTS.md § Issue label taxonomy`). The other three `status:*` labels in this mapping must be added to `scripts/sync_github_labels.sh` and re-synced before the `triage` skill is invoked:

- `status:needs-info`
- `status:ready-for-agent`
- `status:ready-for-human`

The `wontfix` GitHub default label is kept.

## Orthogonal dimensions

The triage state machine uses the `status:*` axis only. Other axes (`priority:*`, `severity:*`, `area:*`, `type:*`) are documented in `AGENTS.md § Issue label taxonomy` and apply independently — a `status:ready-for-agent` issue still carries its `priority:P*`, `area:*`, and `type:*` labels.
