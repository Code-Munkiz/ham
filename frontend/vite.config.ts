import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  const apiProxyTarget = env.VITE_HAM_API_PROXY_TARGET || 'http://127.0.0.1:8000';
  /** Same-origin `/api/*` → FastAPI in dev and `vite preview` (preview does not auto-inherit `server.proxy` in all setups). */
  const apiProxy = {
    '/api': {
      target: apiProxyTarget,
      changeOrigin: true,
    },
  } as const;
  return {
    plugins: [react(), tailwindcss()],
    define: {
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      // Open the system browser when you run `npm run dev` (disable with BROWSER=none).
      open: process.env.BROWSER === 'none' ? false : true,
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modifyâfile watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      proxy: { ...apiProxy },
    },
    preview: {
      proxy: { ...apiProxy },
    },
  };
});
