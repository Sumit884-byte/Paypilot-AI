import { useEffect } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { isDemoPersonaKey } from '../lib/personas'

/** Shareable judge link, e.g. /try/rohan: opens the demo workspace as that persona with no login. */
export function TryDemo() {
  const { persona } = useParams()
  const { session, enterDemo } = useAuth()
  const valid = isDemoPersonaKey(persona)
  const ready = valid && session?.demo && session.persona === persona

  useEffect(() => {
    if (valid && !ready) enterDemo(persona)
  }, [valid, ready, persona, enterDemo])

  if (!valid) return <Navigate to="/" replace />
  return ready ? <Navigate to="/app" replace /> : null
}
