import { fileURLToPath } from 'node:url'
import { loadEnv } from 'vite'

// Reads MULAN_* settings from the repository-root .env; real environment variables take precedence.
const env = loadEnv('', fileURLToPath(new URL('..', import.meta.url)), 'MULAN_')

export const backendPort = env.MULAN_PORT ?? '5001'
export const backendUrl = `http://127.0.0.1:${backendPort}`
