# Future: HAM Local Companion (not implemented)

A small **desktop / tray** helper could:

- Start the local HAM API on login (or on demand), pinned to a known address such as `http://127.0.0.1:8001`.
- Keep the Ham checkout updated (optional `git pull` policy).
- Let the Vercel-hosted HAM UI **auto-detect** a healthy `GET /api/workspace/health` without the user pasting URLs (today’s “Connect local machine” flow is the same probe from the browser).

The web app will never start processes on the operator’s machine by itself; a companion is the natural place to own that.

**Out of scope** for current milestones: no tray app, no auto-installer in this repository until product decides.
