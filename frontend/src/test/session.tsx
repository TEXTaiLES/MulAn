import type { ReactNode } from 'react'
import { SessionContext } from '../context/SessionContext'
import type { Capability, HestiaSession } from '../types'

export function testSession(denied: Capability[] = []): HestiaSession {
  const capabilities = { images_read: true, images_create: true, annotations_read: true, annotations_create: true, annotations_update: true }
  for (const capability of denied) capabilities[capability] = false
  return { authenticated: true, user: { id: 'user-1', email: 'ada@example.com', display_name: 'Ada Lovelace' }, capabilities, login_url: '/auth/login', logout_url: '/auth/logout' }
}

/** Provides a signed-in HESTIA session without calling the session endpoint. */
export function WithSession({ children, denied = [] }: { children: ReactNode; denied?: Capability[] }) {
  const session = testSession(denied)
  return <SessionContext.Provider value={{ session, can: capability => session.capabilities[capability] }}>{children}</SessionContext.Provider>
}
