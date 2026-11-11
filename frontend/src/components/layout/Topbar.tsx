import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Logo } from '../brand/Logo'
import { ThemeToggle } from '../ui/ThemeToggle'
import { Button } from '../ui/Button'
import { PulseDot } from '../ui/Workspace'
import { apiRequest } from '../../lib/api'
import { useAuth } from '../../context/AuthContext'
import { useActivePersona } from '../../lib/personas'
import { PersonaSwitch } from './PersonaSwitch'

export function Topbar({ onMenu: _onMenu }: { onMenu: () => void }) {
  const { session, logout } = useAuth()
  const { applicantId: personaApplicant, linked } = useActivePersona()
  // A linked account has its own applicant id; until it runs PayScore there is no score to show
  const applicantId = linked ? 'linked' : personaApplicant
  // Tagged with its applicant so a persona switch never shows the previous persona's score
  const [live, setLive] = useState<{ applicantId: string; score: number } | null>(null)
  const liveScore = live?.applicantId === applicantId ? live.score : null
  const [scoreUpdated, setScoreUpdated] = useState(false)
  const previousScore = useRef<number | null>(null)

  useEffect(() => {
    if (!session) return
    previousScore.current = null
    const fetchScore = async () => {
      if (linked) {
        // Linked scores come from POST /score/linked and live in this tab, never from a demo persona
        try {
          const own = JSON.parse(sessionStorage.getItem('paypilot.score') || 'null')
          if (own?.linked && typeof own.score === 'number') setLive({ applicantId, score: own.score })
          else setLive(null)
        } catch {}
        return
      }
      try {
        const data = await apiRequest<any>(`/score/live?applicant_id=${applicantId}`)
        if (data?.score !== undefined) {
          if (previousScore.current !== null && previousScore.current !== data.score) {
            setScoreUpdated(true)
            setTimeout(() => setScoreUpdated(false), 4000)
          }
          previousScore.current = data.score
          setLive({ applicantId, score: data.score })
        }
      } catch {}
    }
    fetchScore()
    const timer = setInterval(fetchScore, linked ? 2000 : 8000)
    return () => clearInterval(timer)
  }, [session, applicantId, linked])

  return (
    <header className="z-20 border-b border-[rgb(var(--line))] bg-[rgb(var(--surface))] px-4 sm:px-6 lg:px-10">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-3">
        {/* Narrow phones show only the mark so the controls fit */}
        <Logo wordmarkClassName="hidden min-[420px]:inline-flex" />
        <div className="flex shrink-0 items-center gap-1.5 sm:gap-3">
          {liveScore !== null && (
            <motion.div
              className="hidden items-center gap-2 rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-800 sm:flex"
              whileHover={{ scale: 1.02 }}
            >
              <motion.span
                animate={scoreUpdated ? { scale: [1, 1.5, 1], opacity: [0.6, 1, 0.6] } : {}}
                transition={{ duration: scoreUpdated ? 1 : 0, repeat: scoreUpdated ? 2 : 0 }}
              >
                <PulseDot />
              </motion.span>
              <span className="text-[11px] font-semibold">Live PayScore · {liveScore}</span>
            </motion.div>
          )}
          <PersonaSwitch />
          <span className="hidden rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-semibold text-sky-800 sm:inline-flex">
            {session?.demo ? 'Demo session' : 'PayPal linked'}
          </span>
          <ThemeToggle />
          <Button variant="ghost" className="whitespace-nowrap px-2.5 py-1 text-[11px]" onClick={logout} aria-label="Sign out">
            <span className="hidden sm:inline">Sign out</span> <span aria-hidden="true">↗</span>
          </Button>
        </div>
      </div>
    </header>
  )
}
