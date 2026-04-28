# HAM Desktop — Local Control v1 (spec)

**Status:** **policy / audit / kill-switch / inert sidecar** remains in HAM Desktop. **Historical Electron Phase 4A/4B managed-browser IPC and Linux installer packaging (`npm run pack:linux*`) were removed** from this repository ([`desktop/README.md`](../../desktop/README.md)); server-side automation uses **`/api/browser*`** ([`docs/capabilities/computer_control_pack_v1.md`](../capabilities/computer_control_pack_v1.md)).  
**Product:** Desktop-only Electron shell surfaces (today: **Windows** packaging helpers; developer `npm start` on Linux/macOS). Not the Cloud Run browser operator path for desktop policy.

---

## Product definition

### What Local Control v1 is

A **future** desktop product direction for **permissioned, audited, local-only** operator control of the machine from the **HAM Desktop** (Electron) context: policy, consent, lifecycle, and emergency stop owned by trusted native code; the **renderer stays sandboxed**; risky I/O (browser automation, broad filesystem, shell, etc.) is **not** implemented in Phase 0 and is **not** promised in v1 until explicitly phased.

Hermes and HAM API may **supervise, recommend, or display metadata**; they **do not** become the execution harness for Local Control v1.

### What it is not

- **Not** the hosted HAM web app as the primary control surface for this product.
- **Not** Cloud Run or any remote service as the **desktop local control plane** (including: **`/api/browser` on the public API is not the Desktop Local Control product path** — that route may exist for other purposes; it does not define shipped desktop-local policy or consent).
- **Not** War Room, an in-app browser chrome, or revival of removed browser-operator UI in the frontend.
- **Not** [`ControlPlaneRun`](../CONTROL_PLANE_RUN.md): that substrate stays separate (Cursor/Droid-style control plane read-side); Local Control does not adopt its semantics.
- **Not** a harness provider contract: see [`docs/HARNESS_PROVIDER_CONTRACT.md`](../HARNESS_PROVIDER_CONTRACT.md) for distinct execution lanes.
- **Not** “Hermes runs the machine”: Hermes does not own local execution for this product.
- **Not** OpenCode, Shop **execute / apply / run** actions, or one-click mutation of Hermes config, MCP config, or `.ham` settings from capability rows.

---

## Platform sequence

| Order | Platform | Notes |
|-------|-----------|--------|
| **1** | **Windows** | Packaged Electron (`npm run pack:win*`) remains the installer story. |
| **2** | **Linux / macOS** | **Dev shell** (`cd desktop && npm start`) supported; Linux **AppImage/deb installers removed**. |
| **—** | **macOS** | **Out of scope** unless separately approved. |

---

## Architecture decision (recommended hybrid)

| Layer | Role |
|-------|------|
| **Electron main** | Owns **policy**, **consent**, **audit**, **lifecycle**, and **kill switch**; no inbound network **by default**. |
| **Future local child / sidecar** (not in Phase 0) | Would own **risky I/O** (e.g. browser automation, shell, filesystem) under main-enforced caps — **not** implemented in this milestone. |
| **Renderer** | Sandboxed; **no Node**; only explicit, reviewed preload bridges. |

This is a **design target** for implementation phases; Phase 0 does not add IPC, Playwright, or a sidecar.

---

## Security model (targets for later phases)

- **Default deny** — capabilities off until explicitly enabled.
- **Explicit opt-in** — operator-chosen scope and duration where applicable.
- **Local-only enforcement** — no advertised public remote control endpoint for the desktop product.
- **Allowlists** — fixed presets or narrow capability classes, not arbitrary strings from the model.
- **Permission prompts** — human confirmation for sensitive classes of action.
- **Redacted audit log** — evidence without leaking secrets or full filesystem paths in sync’d UIs.
- **Kill switch** — authoritative stop outside the agent reasoning loop (main / supervisor), revoking session capability.

---

## Capability boundaries

| Area | v1 stance |
|------|-----------|
| **Browser automation** | Out of scope for Phase 0–1; future **desktop-local** alignment only — **not** “cloud API drives the desktop browser” as the product story. |
| **Filesystem access** | Out of scope for early phases except any **doctor/status** style hints; broad access is non-goal until a scoped model exists. |
| **Shell commands** | Desktop M1 allows **allowlisted Hermes CLI presets** only — not generic shell from Local Control v1. |
| **App / window control** | Not in scope for initial phases. |
| **MCP adapters** | Metadata and planning only; no MCP or config mutation from this product line in Phase 0–1. |
| **Screenshots / vision** | Future tier; privacy and policy TBD; not Phase 0. |

---

## Desktop packaging implications

- **Linux installers:** **AppImage/deb pipelines were removed** from this repo; development uses `npm start` only.
- **Windows:** Portable / NSIS via `npm run pack:win*`; plan for **code signing**, AV false positives, and **SmartScreen** friction for unsigned or new publishers.
- **macOS:** Out of scope unless approved separately.

---

## Relationship to existing systems

| System | Relationship |
|--------|----------------|
| **Hermes** | Supervises / recommends / inventory; **does not execute** Local Control actions. |
| **HAM Shop / Capability Library** | May show **read-only metadata**; **cannot execute** local control from directory rows (`apply_available` stays false). |
| **Agent Builder** | May reference capabilities **later**; **cannot drive** local control yet. |
| **ControlPlaneRun** | **Unrelated** — no schema or storage coupling. |
| **`/api/browser` (Cloud Run / API)** | **Not** the desktop product control plane; do not route desktop-local consent or policy through it as if it were Local Control v1. |

---

## Migration from the old War Room / browser UI model

| Topic | Direction |
|-------|-----------|
| **Gone** | War Room, in-app browser operator chrome, and execution UX that implied the web app was the desktop control surface. |
| **Survives** | Concepts: **default deny**, **permission tiers**, **audit**, **kill switch**, **local-first** boundary, **read-only capability directory** as discovery. |
| **Must not return** | Shop/directory **run** CTAs for computer control, revival of War Room, or treating **`/api/browser`** as the shipped **desktop-local** control plane definition. |

---

## Phase plan

| Phase | Scope |
|-------|--------|
| **0** | **Docs + metadata alignment** (this spec, Computer Control Pack surgical updates, capability directory tags/backends). |
| **1** | **Shipped:** read-only **`ham-desktop:local-control-get-status`** IPC + **HAM + Hermes setup** settings card + optional **`ham desktop local-control status`** CLI; **disabled by default**; no automation, generic shell, or filesystem IPC. |
| **2** | **Shipped (skeleton):** persisted **`policy.json`** (default deny, **enabled false**), redacted **audit JSONL**, **kill switch** default engaged + **engage-only** IPC (`ham-desktop:local-control-engage-kill-switch`), expanded status + **`window.hamDesktop.localControl`** narrow bridge; CLI **`local-control policy` / `audit` / `kill-switch engage`** (mirror / noop); still **no** automation. |
| **3A** | **Shipped:** [`local_control_sidecar_protocol_v1.md`](local_control_sidecar_protocol_v1.md) (design) + mock **`sidecar`** status + read-only sidecar IPC (superseded by **3B** for live child shape; see protocol doc history in git). |
| **3B** | **Shipped:** **inert sidecar shell** — stdio child (`health` / `status` / `shutdown` only), main-process manager (single instance); IPC **`getSidecarStatus`**, **`sidecar-start`** (blocked by default kill switch), **`sidecar-stop`**, **`sidecar-health`**; **no** tools, **no** inbound network, **no** Droid access; CLI **`local-control sidecar`** (+ **`health` / `stop` / `start`** stubs = `electron_only`). |
| **3** | **Future:** further narrow automation verticals (**not** restored legacy Linux-only browser IPC). |
| **4A / 4B** | **Removed from repo:** Electron **managed-browser** MVP + Chromium/CDP **IPC stacks** were deleted; aggregate status is **`schema_version` 7** without `browser_*` snapshots. Prefer Ham API **`/api/browser*`** for server-side automation ([`computer_control_pack_v1.md`](../capabilities/computer_control_pack_v1.md)). |
| **4 (future)** | **Windows** packaging + any retargeted local automation is TBD outside this removal milestone. |

---

## Explicit non-goals

- Generic **filesystem**, **process**, or **browser** control from the renderer in Phase 0–1.
- **IPC** expansion, **Playwright**, or a **sidecar** in Phase 0.
- **War Room** or in-app browser **revival**.
- Using **`/api/browser`** on Cloud Run as the **desktop product** control plane.
- Changing **ControlPlaneRun** semantics or making Hermes the **harness anchor**.
- **OpenCode**, Shop **execute / apply / run** buttons, or mutating **Hermes / MCP / `.ham`** settings from this initiative.

---

## References

- [`local_control_sidecar_protocol_v1.md`](local_control_sidecar_protocol_v1.md) — stdio sidecar protocol (Phase 3B: inert shell shipped).
- [`desktop/README.md`](../../desktop/README.md) — Desktop M1 shell (current shipped reality).
- [`docs/capabilities/computer_control_pack_v1.md`](../capabilities/computer_control_pack_v1.md) — pack narrative and permission tiers.
- [`docs/BROWSER_RUNTIME_PLAYWRIGHT.md`](../BROWSER_RUNTIME_PLAYWRIGHT.md) — server-side browser runtime context (distinct from desktop-local product path).
