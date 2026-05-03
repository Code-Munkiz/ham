<!--
PR template for ham. Keep it short; reviewers value clarity over ceremony.
Cloud Agents and HAM VM PRs: see AGENTS.md "Cloud Agent / HAM VM Git policy".
-->

## Summary

<!-- One or two sentences: what changed and why. -->

## Why

<!-- Link the motivating issue, mission, or doc. Examples:
     - Closes #123
     - mission_registry_id: ...
     - droid id / cursor agent id (if relevant)
     - Related: docs/<some-doc>.md
-->

## Scope

- [ ] Code change
- [ ] Docs-only (per AGENTS.md "Cloud Agent PR hygiene", prefer in-place edits)
- [ ] Config / CI change
- [ ] Dependency bump

## Tests / commands run

<!-- Paste the commands you actually ran. Examples:
     - python -m pytest tests/ -q
     - ruff check . && ruff format --check .
     - npm run lint --prefix frontend
     - npm run test:local-control --prefix desktop
-->

```
<output or "n/a">
```

## Screenshots / logs (if UI or runtime change)

<!-- Drag-drop screenshots; paste relevant log excerpts. Redact any secrets. -->

## Risk / rollback

<!-- One sentence: what could go wrong and how to revert. -->

## Checklist

- [ ] No secrets, `.env`, `.ham/`, `.data/`, or live provider data touched
- [ ] No `git push origin main` / force-push from a non-owner-local checkout
- [ ] AGENTS.md / README still accurate (or updated in this PR)
- [ ] Pre-commit hooks pass locally (`pre-commit run --all-files`) if installed
