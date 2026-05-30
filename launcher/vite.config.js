/**
 * Vite configuration for the IAM-OS launcher.
 *
 * The launcher is built as a static bundle and served by the
 * Python web-server (services/web-server) at /. During `npm run dev`
 * Vite proxies API calls to the web-server so the launcher can be
 * developed alongside a locally-running stack.
 */
import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/games': 'http://127.0.0.1:8080',
    },
  },
});
