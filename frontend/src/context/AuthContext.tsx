import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { apiUrl, fetchPaypalStatus, paypalLoginUrl } from '../lib/api'

type Session = {
  linked: boolean
  demo: boolean
  persona: string
  at: string
  /** What a PayPal-linked user asked to be called; PayPal sign-in deliberately shares no name */
  displayName?: string
}

type AuthContextValue = {
  session: Session | null
  isAuthed: boolean
  loginWithPaypal: () => Promise<'redirect' | 'unavailable'>
  enterDemo: (persona?: string) => void
  completeLink: () => void
  setDisplayName: (name: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)
const STORAGE_KEY = 'paypilot.session'

function clearWorkspaceState() {
  try {
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith('paypilot.') && key !== STORAGE_KEY)
      .forEach((key) => sessionStorage.removeItem(key))
  } catch {}
}

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
      enterDemo: (persona = 'priya') => {
        // The API answers from the linked PayPal cookie when one exists; a demo must not see the user's account
        void fetch(apiUrl('/paypal/unlink'), { method: 'POST' }).catch(() => {})
        if (session?.persona !== persona || !session?.demo) clearWorkspaceState()
        persist({ linked: true, demo: true, persona, at: new Date().toISOString() })
      },
      completeLink: () => {
        clearWorkspaceState()
        persist({ linked: true, demo: false, persona: 'priya', at: new Date().toISOString() })
      },
      setDisplayName: (name: string) => {
        if (session) persist({ ...session, displayName: name.trim() })
      },
      logout: () => {
        // The linked PayPal account lives in an HttpOnly cookie only the API can clear
        if (session && !session.demo) void fetch(apiUrl('/paypal/unlink'), { method: 'POST' }).catch(() => {})
        clearWorkspaceState()
        persist(null)
      },
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
