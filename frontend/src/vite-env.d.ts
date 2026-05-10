/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_HAM_API_BASE?: string;
  /** Vite dev only: proxy `/api` to this origin (default `http://127.0.0.1:8000`). */
  readonly VITE_HAM_API_PROXY_TARGET?: string;
  /** When true, enables the namespaced Hermes Workspace lift at `/workspace/*` (scaffold; see docs). */
  readonly VITE_ENABLE_HERMES_WORKSPACE?: string;
  /** Desktop dev-only: surface GOHAM internals in the Workspace UI when also in Vite DEV. */
  readonly VITE_HAM_SHOW_GOHAM_DEV_TOOLS?: string;
  /**
   * DEV + localhost only: mock workspace/me context without Clerk so `/workspace/*` UI can be QA’d locally.
   * Never enforced in production builds.
   */
  readonly VITE_HAM_LOCAL_DEV_WORKSPACE_BYPASS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
