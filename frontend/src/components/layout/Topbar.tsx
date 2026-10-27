import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Logo } from '../brand/Logo'
import { ThemeToggle } from '../ui/ThemeToggle'
import { Button } from '../ui/Button'
import { PulseDot } from '../ui/Workspace'
import { apiRequest } from '../../lib/api'
import { useAuth } from '../../context/AuthContext'

const APPLICANT_ID = 'PSC-PRIYA-001'

export function Topbar({ onMenu }: { onMenu: () => void }) {
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
    <header className="sticky top-0 z-20 flex h-12 items-center justify-between gap-3 border-b border-white/[.07] bg-[#080f1c] px-4 sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          className="rounded-xl p-2 hover:bg-white/10 lg:hidden"
          onClick={onMenu}
          aria-label="Open navigation"
        >
          <span className="mb-1 block h-0.5 w-5 bg-current" />
          <span className="mb-1 block h-0.5 w-5 bg-current" />
          <span className="block h-0.5 w-4 bg-current" />
        </button>
        <Logo compact />
      </div>
      <div className="flex items-center gap-3">
        {liveScore !== null && (
          <motion.div
            className="flex items-center gap-2 rounded-full border border-paypal/20 bg-paypal/10 px-2.5 py-1"
            whileHover={{ scale: 1.02 }}
          >
            <motion.span
              animate={scoreUpdated ? { scale: [1, 1.5, 1], opacity: [0.6, 1, 0.6] } : {}}
              transition={{ duration: scoreUpdated ? 1 : 0, repeat: scoreUpdated ? 2 : 0 }}
            >
              <PulseDot className={scoreUpdated ? 'bg-emerald-500' : ''} />
            </motion.span>
            <span className="text-xs font-mono font-bold text-paypal">{liveScore}</span>
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">PayScore</span>
            {scoreUpdated && (
              <motion.span
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400"
              >
                Updated
              </motion.span>
            )}
          </motion.div>
        )}
        <span className="hidden rounded-full bg-paypal/10 px-3 py-1 text-xs font-semibold text-paypal sm:inline">
          {session?.demo ? 'Demo session' : 'PayPal linked'}
        </span>
        <ThemeToggle />
          <Button variant="ghost" className="px-2.5 py-1 text-[11px]" onClick={logout}>
          Sign out
        </Button>
      </div>
    </header>
  )
}
