import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { AmbientBackground } from '../components/ui/AmbientBackground'
import { Button } from '../components/ui/Button'
import { Logo } from '../components/brand/Logo'
import { Skeleton } from '../components/ui/Skeleton'

export function AuthCallback() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { completeLink, enterDemo } = useAuth()
  const error = params.get('error')
  const linked = params.get('linked') === 'true'
  // completeLink changes the session, which gives completeLink a new identity and re-runs this effect;
  // link once so that loop cannot spin before the navigation to /app lands
  const linkedOnce = useRef(false)

  useEffect(() => {
    if (linked) {
      if (!linkedOnce.current) {
        linkedOnce.current = true
        completeLink()
      }
      navigate('/app', { replace: true })
      return
    }
    if (!error) {
      const timer = window.setTimeout(() => navigate('/', { replace: true }), 1200)
      return () => window.clearTimeout(timer)
    }
    return undefined
  }, [completeLink, error, linked, navigate])

  if (error) {
    return (
      <div className="relative flex min-h-svh flex-col items-center justify-center gap-4 bg-[rgb(var(--bg))] px-6 text-center">
        <AmbientBackground />
        <div className="relative z-10 max-w-md space-y-4">
          <Logo compact />
          <p className="text-lg font-semibold">PayPal linking did not complete</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">{error.replaceAll('_', ' ')}</p>
          <div className="flex flex-wrap justify-center gap-3">
            <Button onClick={() => navigate('/')}>Back to landing</Button>
            <Button
              variant="ghost"
              onClick={() => {
                enterDemo('priya')
                navigate('/app')
              }}
            >
              Continue with demo data
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center gap-4 bg-[rgb(var(--bg))]">
      <AmbientBackground />
      <div className="relative z-10 flex flex-col items-center gap-4">
        <Logo compact />
        <Skeleton className="h-12 w-56" />
        <p className="text-sm text-slate-500">Finishing PayPal login…</p>
      </div>
    </div>
  )
}
