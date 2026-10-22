import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { backendUrl } from './mulan.env.ts'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Keep the browser's Host header so the HESTIA login returns to this dev server.
    proxy: { '/api': { target: backendUrl, changeOrigin: false }, '/auth': { target: backendUrl, changeOrigin: false } },
  },
})
