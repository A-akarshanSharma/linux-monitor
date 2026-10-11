import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { appShellPlugin } from './pwa/plugin.js'
import { readFileSync } from 'node:fs'

// Use the same release version as the bundled backend, baked into the UI so a
// cached frontend can be distinguished from the API currently serving it.
const versionSource = readFileSync(new URL('../backend/app/__init__.py', import.meta.url), 'utf8')
const appVersion = versionSource.match(/^__version__\s*=\s*["']([^"']+)["']/m)?.[1]
if (!appVersion) throw new Error('Missing application release version')

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_BACKEND_URL || 'http://localhost:8000'

  return {
    define: { __APP_VERSION__: JSON.stringify(appVersion) },
    plugins: [react(), appShellPlugin()],
    server: {
      // The app only ever calls relative /api/... paths (see src/api/client.js);
      // in dev this proxy forwards them server-side to the FastAPI backend, so the
      // browser never makes a cross-origin request and the backend needs no CORS
      // configuration. In production (Phase 7) nginx plays the same role.
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    preview: {
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
  }
})
