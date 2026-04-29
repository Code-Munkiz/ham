# Hermes Workspace — full IA inventory (row-ID baseline)

**Status:** implementation tracking contract (audit-derived).  
**Upstream evidence:** `repomix-output-outsourc-e-hermes-workspace.git.txt` (read-only).  
**HAM namespaced app:** `frontend/src/features/hermes-workspace/`.

**Schema**

```text
ID | Area | Upstream file(s) | Visible label | Type | Parent/group | Route/action | Current HAM status | Lift target | Notes
```

**`Lift target` values:** `Lift UI now` | `Lift behavior now` | `Needs HAM adapter` | `Needs backend/runtime bridge` | `Needs explicit approval only if it exposes secrets or breaks existing HAM contracts` | `Unverified`

**Adapter names (planned in HAM):** `workspaceFileAdapter`, `workspaceTerminalAdapter` — centralize bridge gaps; do not scatter “blocked” copy in product UI.

---

## SHELL (shell / chrome / global)

| ID | Upstream file(s) | Visible label | Type | Parent | Route / action | HAM (snapshot) | Lift target | Notes |
|----|------------------|---------------|------|--------|----------------|----------------|-------------|--------|
| SHELL-001 | `src/components/workspace-shell.tsx` | (layout) | layout | root | all | `WorkspaceShell` partial | Lift UI now | Sidebar + outlet |
| SHELL-002 | `src/components/workspace-shell.tsx` | (Electron title) | chrome | top | n/a | Unverified | Unverified | `isElectron` in upstream |
| SHELL-003 | `src/components/hermes-reconnect-banner.tsx` | (reconnect) | banner | top | | absent | Needs HAM adapter | |
| SHELL-004 | `src/components/connection-startup-screen.tsx` | (startup) | overlay | gate | | absent | Needs HAM adapter | |
| SHELL-005 | `src/components/workspace-shell.tsx` | Collapse backdrop | button | nav | | no equivalent | Lift UI now | |
| SHELL-006 | `src/components/workspace-shell.tsx` | `ChatSidebar` | region | main | | HAM custom sidebar | Lift UI now | |
| SHELL-007 | `src/components/chat-panel.tsx` | Chat panel / toggle | panel | right | | absent | Lift UI later | |
| SHELL-008 | `src/components/mobile-page-header.tsx` | Mobile title | header | mobile | | `workspacePathTitle` | Lift UI now | |
| SHELL-009 | `src/components/mobile-tab-bar.tsx` | Home…Settings tabs | tab bar | bottom | | implement under `/workspace` | Lift UI now | 9 items; no Tasks/Cond/Ops in bar |
| SHELL-010 | `src/components/mobile-hamburger-menu.tsx` | Nav drawer | drawer | mobile | | hamburger+drawer in shell | Lift UI now | `NAV_ITEMS` includes more routes |
| SHELL-011 | `src/components/workspace-shell.tsx` | `getTabIndex` / slide | logic | mobile | | risk | Unverified | Order vs `TABS` skew for cond/ops |
| SHELL-012 | `src/components/workspace-shell.tsx` | `fetch('/api/sessions')` | data | | | `workspaceSessionAdapter` | Needs HAM adapter | |
| SHELL-013 | `src/components/command-palette.tsx` | Command palette | modal | | | not in HAM | Lift UI now | |
| SHELL-014 | `src/hooks/use-swipe-navigation.ts` | Swipe | gesture | | | Unverified | Unverified | |
| SHELL-015 | `src/components/terminal-panel.tsx` | Terminal dock | panel | bottom | chat | optional embed | Lift UI now | Min/max/close, resize |

---

## SESS (search / new session / sidebar)

| ID | Upstream file(s) | Visible label | HAM | Lift / Notes |
|----|------------------|---------------|-----|--------------|
| SESS-001 | `chat-sidebar.tsx` | Search | HAM: session filter | Modal vs filter |
| SESS-002 | `chat-sidebar.tsx` | New Session | `/workspace/chat` | Route model differs |
| SESS-003 | `chat-sidebar.tsx` | Brand / Hermes | yes | |
| SESS-004–015 | `chat-sidebar.tsx` | Main + Knowledge nav | `workspaceNavConfig` | `/workspace/*` |
| SESS-016–019 | `session-item.tsx` | Pin / Rename / Delete | no row menu | Destructive → approval |
| SESS-020 | `sidebar-sessions.tsx` | Pinned + list | flat list | |
| SESS-021 | `chat-sidebar.tsx` | `ThemeToggleMini` | not in shell | |

---

## FILES

| ID | Upstream | Label / control | HAM | Bridge |
|----|----------|------------------|-----|--------|
| FILES-001 | `routes/files.tsx` | Files title | route | |
| FILES-002 | `routes/files.tsx` | Show/Hide explorer | | |
| FILES-003 | `routes/files.tsx` | Monaco editor | | textarea/monaco in lift |
| FILES-004–007 | `file-explorer-sidebar.tsx` | Workspace, toolbar, search, tree | | `workspaceFileAdapter` |
| FILES-008 | same | Context menu (rename…delete) | | same |
| FILES-009 | same + dialogs | Preview / prompts | | |
| FILES-010 | `files.tsx` | Insert reference | | adapter |

---

## TERM

| ID | Upstream | Label / control | HAM | Bridge |
|----|----------|------------------|-----|--------|
| TERM-001 | `routes/terminal.tsx` | Page | | |
| TERM-002–006 | `terminal-workspace.tsx` | Tabs, debug, new, panel controls, tab menu | | `workspaceTerminalAdapter` |
| TERM-007–008 | `terminal-workspace.tsx` | `terminal-input` / `terminal-resize` | | bridge |
| TERM-009 | `mobile-terminal-input.tsx` | mobile input, paste, ^C, send | | bridge |
| TERM-010 | `terminal-panel.tsx` | Dock resize / navigate | | |
| TERM-011 | `debug-panel.tsx` | Debug analyzer | | |

---

## JOBS / TASKS / COND / OPS / MEM / SKILLS / PROFILES / SETTINGS

Summarized; see audit thread for per-card rows. **Settings:** `settings-sidebar.tsx` (`SETTINGS_NAV_ITEMS`), `routes/settings/index.tsx`, `settings/mcp.tsx`, `settings/providers.tsx`. **`/workspace/settings`:** missing in HAM `WorkspaceApp`.

**Second repomix pass** before implementing Profiles, Operations, Conductor, or Skills Featured: eliminate remaining `Unverified` rows in those areas.

---

## HAM snapshot (`/workspace/*`)

- Shell + nav + session list (HAM APIs); chat streaming via `workspaceChatAdapter` / `workspaceSessionAdapter`.
- Dashboard: `WorkspaceHome`.
- Other top-level routes were placeholders until Files/Terminal lift; **`workspaceFileAdapter` / `workspaceTerminalAdapter`** added as the single bridge surface.

---

## Do not (product / engineering)

- No browser-side secrets; no client privileged credentials.
- No upstream `hermes-proxy` copy; no TanStack server routes in HAM client.
- Do not promote `/workspace` over existing product routes by default.
- Files/Terminal: do not replace full surfaces with placeholder cards; keep controls visible; neutral copy only for bridge gaps.
