# HAM Desktop — tagged release pipeline

## Product guardrails

- **No silent auto-update** (`electron-updater` intentionally not used). Releases ship binaries **only** via GitHub Release assets + honest manifest/metadata.
- **Unsigned / internal**: Windows portable remains **unsigned** unless you add signing; do not label drafts as production-signed.
- **Local control / GOHAM**: this pipeline only runs `npm run pack:win` and uploads artifacts — it does **not** change preload, bridge, pairing, or policy code paths.

## Triggers

| Trigger | Behaviour |
|---------|-----------|
| **Push tag** `desktop-v*` | Validates `desktop/package.json` **`version`** matches the tag (**`desktop-v`**`x.y.z` ⇔ **`x.y.z`**), packs Windows portable, writes **`.exe.sha256`**, creates **GitHub Release** with exe + checksum sidecars, appends manifest hints to Job Summary |
| **`workflow_dispatch`** | Same pack + checksum steps; uploads **`desktop/dist-pack/*`** as a **workflow artifact** only (**no Release**) — use for CI smoke |

**Not**: every merge to `main` does **not** publish desktops.

## Windows artifact layout

electron-builder emits (see `desktop/package.json` → `build.win.*`):

- `HAM-Desktop-{version}-Win-x64-Portable.exe`
- Companion `*.exe.sha256` produced in CI (`Get-FileHash` → `basename.exe.sha256`).

## Release checklist (maintainer)

1. **Bump version** first: edit **`desktop/package.json`** `version` to `x.y.z` (canonical semver for **`app.getVersion()`**).
2. **Commit** the bump (often with `frontend/package.json`/changelog if coordinated).
3. **Tag**: `git tag desktop-vx.y.z` and **`git push origin desktop-vx.y.z`**.
4. Wait for **Desktop release** workflow success.
5. **Update manifests** — still **manual**, still **dual file** until automation is approved:

   - `frontend/public/desktop-downloads.json`
   - `frontend/src/lib/ham/desktop-downloads.manifest.json` (bundled twin; **prevent drift** by editing both together or scripted copy).

   Copy **SHA-256** from Release asset `*.exe.sha256` or Job Summary snippet. Use **Downloads** URLs of the form  
   `https://github.com/<org>/<repo>/releases/download/desktop-vx.y.z/HAM.Desktop-x.y.z-*` (**match exact asset names** Release uploaded).

6. Deploy web(Vercel) so `public/desktop-downloads.json` updates for landing + **`raw.githubusercontent.com`** eventual consistency for Electron’s update check fetch.

### Manifest platforms (Windows-first)

**This workflow publishes Windows portable `.exe` + `.sha256` only** — see **[`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md)**. It does **not** build **NSIS** installers.

Maintainers edit **`frontend/public/desktop-downloads.json`** (and the bundled twin) manually after a tag. Today **`platforms.windows`** holds the portable artifact; **`platforms.linux`** and **`platforms.macos`** are **`null`** — there is **no** Linux desktop row to refresh from this pipeline. Restoring Linux or macOS **packaged** artifacts would be a deliberate product + CI decision (new targets and jobs), not implied by older Release files.

### Checksum strategy

| Layer | Approach |
|-------|----------|
| **CI** | SHA-256 of final `.exe` before upload |
| **Registry** | `*.sha256` text next to exe on Release (mirror old `desktop-v0.1.2` pattern) |
| **Manifest JSON** | `platforms.windows.sha256` full hex lowercase (what landing UX shows) |

## Rollback

1. **Bad binary**: delete **Release** draft/asset or publish a corrective tag **`desktop-vx.y.(z+1)`** — never downgrade semver in manifest.
2. **Bad manifest**: revert the commit touching `frontend/public/desktop-downloads.json` + twin snapshot; redeploy web.
3. **Bad tag**: Git **delete tag** remote/local only if no users rely on URLs; preferably ship a newer tag.

## Tokens & permissions

- Workflow uses default **`GITHUB_TOKEN`** with **`permissions: contents: write`** (releases + uploads). forks from outside contributors cannot push tags to canonical repo anyway.
- If you fork: enable **Actions** tab and **`Allow GitHub Actions to create and approve pull requests`** **off** unless you use an explicit bot PAT for PR workflows (not shipped here).

## Decision template

Fill after review:

```text
Pipeline status: READY_TO_IMPLEMENT_RELEASE_PIPELINE (Windows portable tag-only) /
                  KEEP_MANUAL_RELEASE_FOR_NOW /
                  NO_GO

Non-Windows packaged desktop: not published from this repo (see SUPPORT_MATRIX.md)
Manifest auto-merge: KEEP_MANUAL (documented above)
```

Current recommendation: **`READY_TO_IMPLEMENT_RELEASE_PIPELINE`** for **Windows portable** **tag pushes** **`+`** **manual manifest** update afterward. **NSIS** and **non-Windows** packaged desktops stay **out of this workflow** until explicitly scoped.
