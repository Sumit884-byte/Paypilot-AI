import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Logo } from '../brand/Logo'
import { ThemeToggle } from '../ui/ThemeToggle'
import { Button } from '../ui/Button'
import { PulseDot } from '../ui/Workspace'
import { apiRequest } from '../../lib/api'
import { useAuth } from '../../context/AuthContext'

const APPLICANT_ID = 'PSC-PRIYA-001'

export function Topbar({ onMenu: _onMenu }: { onMenu: () => void }) {
  const { session, logout } = useAuth()
  const [liveScore, setLiveScore] = useState<number | null>(null)
  const [scoreUpdated, setScoreUpdated] = useState(false)
  const previousScore = useRef<number | null>(null)

  useEffect(() => {
    if (!session) return
    const fetchScore = async () => {
      try {
        const data = await apiRequest<any>(`/score/live?applicant_id=${APPLICANT_ID}`)
        if (data?.score !== undefined) {
          if (previousScore.current !== null && previousScore.current !== data.score) {
            setScoreUpdated(true)
            setTimeout(() => setScoreUpdated(false), 4000)
          }
          previousScore.current = data.score
          setLiveScore(data.score)
        }
      } catch {}
    }
    fetchScore()
    const timer = setInterval(fetchScore, 8000)
    return () => clearInterval(timer)
  }, [session])

  return (
    <header className="z-20 border-b border-[rgb(var(--line))] bg-[rgb(var(--surface))] px-4 sm:px-6 lg:px-10">
      <div className="mx-auto flex h-16 max-w-[1600px] items-center justify-between gap-3">
        <Logo />
        <div className="flex items-center gap-2 sm:gap-3">
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
          <span className="hidden rounded-full bg-sky-50 px-2.5 py-1 text-[11px] font-semibold text-sky-800 sm:inline-flex">
            {session?.demo ? 'Demo session' : 'PayPal linked'}
          </span>
          <ThemeToggle />
          <Button variant="ghost" className="px-2.5 py-1 text-[11px]" onClick={logout}>
            Sign out ↗
          </Button>
        </div>
      </div>
    </header>
  )
}
