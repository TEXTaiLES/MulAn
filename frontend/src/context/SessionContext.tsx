import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiFailure, signIn } from '../api/client'
import type { Capability, HestiaSession } from '../types'

export interface SessionValue { session: HestiaSession; can: (capability: Capability) => boolean }

export const SessionContext = createContext<SessionValue | null>(null)

type State = { status: 'loading' } | { status: 'redirecting' } | { status: 'ready'; session: HestiaSession } | { status: 'error'; message: string }

/** Renders the app only for signed-in HESTIA users; everyone else is sent to the HESTIA portal. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const load = useCallback(() => {
    setState({ status: 'loading' })
    api.session().then(session => { if (session.authenticated) setState({ status: 'ready', session }); else { setState({ status: 'redirecting' }); signIn(session.login_url) } }).catch(reason => setState({ status: 'error', message: reason instanceof ApiFailure ? reason.message : 'HESTIA could not be reached.' }))
  }, [])
  useEffect(load, [load])
  if (state.status === 'loading') return <div className="page narrow"><p className="loading">Checking your HESTIA sign-in…</p></div>
  if (state.status === 'redirecting') return <div className="page narrow"><p className="loading">Redirecting to the HESTIA sign-in page…</p></div>
  if (state.status === 'error') return <div className="page narrow"><p className="error" role="alert">{state.message}</p><button className="primary" onClick={load}>Try again</button></div>
  const session = state.session
  return <SessionContext.Provider value={{ session, can: capability => session.capabilities[capability] }}>{children}</SessionContext.Provider>
}

export function useSession() {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside SessionProvider')
  return value
}
