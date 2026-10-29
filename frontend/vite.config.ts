import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import pwa from './build/pwa.ts'

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL('../', import.meta.url))
  const env = { ...loadEnv(mode, root, ''), ...process.env }
  return {
    plugins: [react(), pwa()],
    server: {
      port: Number(env.VITE_PORT ?? 5173),
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${env.APP_PORT ?? 8000}`,
          // Keep the browser's Host so the API can validate same-origin writes.
          changeOrigin: false,
        },
      },
    },
  }
})
