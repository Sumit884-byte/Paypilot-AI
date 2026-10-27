import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Logo } from '../components/brand/Logo'
import { FloatingCards } from '../components/landing/FloatingCards'
import { PayPalLoginButton } from '../components/landing/PayPalLoginButton'
import { AmbientBackground } from '../components/ui/AmbientBackground'
import { SandboxBadge } from '../components/ui/SandboxBadge'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { Button } from '../components/ui/Button'
import { GlassCard } from '../components/ui/GlassCard'
import { useAuth } from '../context/AuthContext'
import { fadeUp, stagger } from '../lib/motion'

const stats = [
  ['300–850', 'PayScore scale'],
  ['12 mo', 'income window'],
  ['Sandbox', 'PayPal only'],
]

const steps = [
  { n: '01', title: 'Link sandbox PayPal', copy: 'OAuth into a sandbox seller. Live lending never happens here.' },
  { n: '02', title: 'Read the cashflow', copy: 'Income, disputes, refunds, and invoices become a 12-month profile.' },
  { n: '03', title: 'See a PayScore', copy: 'A 300–850 copilot score with a labelled demo caveat — not a bank decision.' },
]

export function Landing() {
  const { isAuthed, loginWithPaypal, enterDemo } = useAuth()
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  if (isAuthed) return <Navigate to="/app" replace />

  async function onLogin() {
    setBusy(true)
    setNotice(null)
    const result = await loginWithPaypal()
    if (result === 'unavailable') {
      setNotice('PayPal sandbox is not configured on the API. You can still tour the cockpit with demo data.')
      setBusy(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden bg-[rgb(var(--bg))]">
      <AmbientBackground />

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between gap-3 px-5 py-5">
        <Logo compact />
        <div className="flex items-center gap-3">
          <SandboxBadge className="hidden sm:inline-flex" />
          <ThemeToggle />
        </div>
      </header>

      <motion.main
        variants={stagger}
        initial="initial"
        animate="animate"
        className="relative z-10 mx-auto grid max-w-6xl items-center gap-10 px-5 pb-16 pt-4 lg:grid-cols-[1.08fr_0.92fr] lg:pt-8"
      >
        <div>
          <motion.div variants={fadeUp} className="sm:hidden">
            <SandboxBadge />
          </motion.div>
          <motion.p
            variants={fadeUp}
            className="mt-5 text-xs font-semibold uppercase tracking-[0.28em] text-paypal"
          >
            For the independent economy
          </motion.p>
          <motion.h1
            variants={fadeUp}
            className="mt-4 max-w-[18ch] font-display text-[2.05rem] font-extrabold leading-[1.12] tracking-tight sm:max-w-none sm:text-5xl"
          >
            <span className="text-gradient-hero">
              Your income has a story. Give it a score.
            </span>
          </motion.h1>
          <motion.p variants={fadeUp} className="mt-5 max-w-lg text-base leading-relaxed text-slate-600 dark:text-slate-300 sm:text-lg">
            No traditional credit history? Explore a demo score built around your PayPal income — not your employment status.
          </motion.p>
          <motion.div variants={fadeUp} className="mt-8 flex flex-col items-start gap-4 sm:flex-row sm:items-center">
            <PayPalLoginButton onClick={onLogin} busy={busy} />
            <Button variant="ghost" className="border-paypal/20" onClick={enterDemo}>
              Tour the cockpit
            </Button>
          </motion.div>
          {notice && (
            <motion.p variants={fadeUp} className="mt-4 max-w-md text-sm text-amber-700 dark:text-amber-glow">
              {notice}
            </motion.p>
          )}
          <motion.div variants={fadeUp} className="mt-10 grid max-w-lg grid-cols-3 gap-3">
            {stats.map(([value, label]) => (
              <GlassCard key={label} className="px-3 py-4 text-center">
                <p className="text-lg font-bold">{value}</p>
                <p className="text-[11px] uppercase tracking-wider text-slate-500">{label}</p>
              </GlassCard>
            ))}
          </motion.div>
        </div>
        <motion.div variants={fadeUp}>
          <FloatingCards />
        </motion.div>
      </motion.main>

      <motion.section
        variants={stagger}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, amount: 0.3 }}
        className="relative z-10 mx-auto grid max-w-6xl gap-4 px-5 pb-20 md:grid-cols-3"
      >
        {steps.map((step) => (
          <motion.div key={step.n} variants={fadeUp}>
            <GlassCard className="h-full">
              <p className="text-xs font-bold tracking-[0.2em] text-paypal">{step.n}</p>
              <h2 className="mt-2 text-lg font-semibold">{step.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400">{step.copy}</p>
            </GlassCard>
          </motion.div>
        ))}
      </motion.section>

      <footer className="relative z-10 border-t border-navy-900/5 px-5 py-8 text-center text-xs text-slate-500 dark:border-white/10 dark:text-slate-400">
        Paypilot AI is a sandbox demo. Scores are not credit decisions. No real lending, disbursement, or repayment.
      </footer>
    </div>
  )
}
