import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { backendUrl } from './mulan.env.ts'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': backendUrl },
  },
})
