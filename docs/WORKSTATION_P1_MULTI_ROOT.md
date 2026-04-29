# P1 (deferred): multiple filesystem roots

Not implemented. Single `HAM_WORKSPACE_ROOT` (or `HAM_WORKSPACE_FILES_ROOT` / sandbox) is the only supported model in P0.

If multi-root is required later, agree on the following before coding:

- **Env shape:** e.g. `HAM_WORKSPACE_ROOTS` as JSON array of absolute paths, or a delimiter-separated list with Windows-safe parsing.
- **Path disambiguation:** relative API paths must map to exactly one root (e.g. prefix `vol1/foo` vs `foo` with ordered roots) or use explicit `rootId` in the request.
- **Windows:** drive letters, junctions, and symlink policy (follow vs block) for each root.
- **API:** `list` / read / write / tree responses must include which root a path belongs to if ambiguous.
- **UI:** root selector, labels in the file tree, and per-root broad-warning badges if needed.
- **Tests:** traversal across roots, collision cases, and mount-order edge cases.

Do not ship a partial list.
