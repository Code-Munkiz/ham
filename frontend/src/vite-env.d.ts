/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_HAM_API_BASE?: string;
  /** Vite dev only: proxy `/api` to this origin (default `http://127.0.0.1:8000`). */
  readonly VITE_HAM_API_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
