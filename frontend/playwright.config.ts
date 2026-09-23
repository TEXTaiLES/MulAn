import { defineConfig } from '@playwright/test'
import { backendPort, backendUrl } from './mulan.env.ts'

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  webServer: [
    { command: `python -m flask --app backend.mulan.wsgi run --host 127.0.0.1 --port ${backendPort}`, cwd: '..', url: `${backendUrl}/api/health`, reuseExistingServer: true, timeout: 120_000 },
    { command: 'npm run dev -- --host 127.0.0.1', cwd: '.', url: 'http://127.0.0.1:5173', reuseExistingServer: true, timeout: 120_000 },
  ],
})
