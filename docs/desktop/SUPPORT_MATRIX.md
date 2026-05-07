# HAM Desktop — support matrix (Windows-first)

Concise product-truth for **packaged** HAM Desktop. For local-control semantics, see [`local_control_v1.md`](local_control_v1.md). For release mechanics, see [`RELEASE_PIPELINE.md`](RELEASE_PIPELINE.md).

| Distribution / path | Status | Notes |
|---------------------|--------|--------|
| **Windows x64 portable `.exe`** | **Supported** (internal) | Shipped via **GitHub Release** on `desktop-v*` tags and referenced from **`frontend/public/desktop-downloads.json`** (and its bundled twin under `frontend/src/lib/ham/`). **Not code-signed** unless/until signing is added — treat as **unsigned internal** builds. |
| **Windows x64 NSIS setup `.exe`** | **Manual / maintainer only** | Build with **`npm run pack:win:nsis`** from `desktop/` (may require **Wine** on Linux or a Windows host). **Not** produced by **`.github/workflows/desktop-release.yml`** today; the tag workflow uploads **portable** `.exe` + **`.sha256`** only. |
| **macOS** | **Not published** | Manifest **`platforms.macos`** is **`null`**. Contributors may run from **source** (`npm start` in `desktop/`) — **not** a product install path. |
| **Linux desktop installers** | **Not published** | Manifest **`platforms.linux`** is **`null`**. **`pack:linux`** is removed from this repo. **No** Linux update prompt from the manifest. |
| **Linux / macOS dev shell** | **Contributor / dev-local only** | **`cd desktop && npm start`** (see [`desktop/README.md`](../../desktop/README.md)). Same renderer as the web app in dev; **not** a supported installer or release channel. |
| **Historical GitHub Release assets** | **Not current product** | Older **Release** files may still exist on GitHub. They are **not** the canonical supported matrix unless this doc and [`desktop-downloads.json`](../../frontend/public/desktop-downloads.json) say so. |

**Summary:** **Windows portable** is the only **CI-published** desktop artifact today. Everything else in this table is **out of scope** for “supported download” unless explicitly re-opened as a packaging decision.
