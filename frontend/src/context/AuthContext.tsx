import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { fetchPaypalStatus, paypalLoginUrl } from '../lib/api'

type Session = {
  linked: boolean
  demo: boolean
  persona: string
  at: string
}

type AuthContextValue = {
  session: Session | null
  isAuthed: boolean
  loginWithPaypal: () => Promise<'redirect' | 'unavailable'>
  enterDemo: () => void
  completeLink: () => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)
const STORAGE_KEY = 'paypilot.session'

function readSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(readSession)

  const persist = useCallback((next: Session | null) => {
    setSession(next)
    if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    else sessionStorage.removeItem(STORAGE_KEY)
  }, [])

  const loginWithPaypal = useCallback(async (): Promise<'redirect' | 'unavailable'> => {
    try {
      const status = await fetchPaypalStatus()
      if (!('paypal' in status) || status.paypal !== 'ok') return 'unavailable'
    } catch {
      return 'unavailable'
    }
    window.location.assign(paypalLoginUrl())
    return 'redirect'
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthed: Boolean(session?.linked),
      loginWithPaypal,
      enterDemo: () => persist({ linked: true, demo: true, persona: 'priya', at: new Date().toISOString() }),
      completeLink: () => persist({ linked: true, demo: false, persona: 'priya', at: new Date().toISOString() }),
      logout: () => persist(null),
    }),
    [loginWithPaypal, persist, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
