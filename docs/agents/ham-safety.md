# HAM Safety Addendum for Local Skills

These constraints apply whenever local skills are used in this repository:

- Never claim live acceptance from unit tests alone.
- Signed-in browser validation must be honest.
- If automation lacks a Clerk session, classify as `MANUAL SESSION REQUIRED` (not `PASS`).
- If `CLERK_SESSION_INVALID` persists after refresh/sign-in, classify as `AUTH SESSION BLOCKER`; report endpoint/status/error code only.
- Never leak raw tokens, cookies, auth headers, signed URLs, or internal runtime URLs.
- No broad soak testing until focused gates pass.
- Do not move to export ZIP or GitHub push until Builder iteration, preview lifecycle, and workspace cleanup are stable.
- For Cloud Run, prefer image-only deploys; do not use env-file redeploys unless explicitly approved.
- Do not use `--set-env-vars` unless explicitly approved.
