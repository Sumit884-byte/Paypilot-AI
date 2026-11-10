import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Logo } from '../components/brand/Logo'
import { FloatingCards } from '../components/landing/FloatingCards'
import { PayPalLoginButton } from '../components/landing/PayPalLoginButton'
import { AmbientBackground } from '../components/ui/AmbientBackground'
import { SandboxBadge } from '../components/ui/SandboxBadge'
import { Button } from '../components/ui/Button'
import { useAuth } from '../context/AuthContext'
import { fadeUp, stagger } from '../lib/motion'

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

      <header className="relative z-10 mx-auto flex w-full max-w-[1600px] items-center justify-between gap-3 px-5 py-5 lg:px-10">
        <Logo compact />
        <div className="flex items-center gap-3">
          <SandboxBadge className="hidden sm:inline-flex" />
        </div>
      </header>

      <motion.main
        variants={stagger}
        initial="initial"
        animate="animate"
        className="relative z-10 mx-auto grid w-full max-w-[1600px] items-center gap-6 px-5 pb-8 pt-5 sm:gap-10 lg:grid-cols-[1.05fr_.95fr] lg:px-10 lg:pb-12 lg:pt-8"
      >
        <div>
          <motion.div variants={fadeUp} className="sm:hidden">
            <SandboxBadge />
          </motion.div>
          <motion.p
            variants={fadeUp}
            className="mt-5 text-[10px] font-semibold uppercase text-paypal"
          >
            Your work is independent. Your story matters.
          </motion.p>
          <motion.h1
            variants={fadeUp}
            className="mt-3 max-w-[13ch] font-display text-5xl leading-[.98] sm:text-6xl lg:text-[4.5rem]"
          >
            <span className="text-gradient-hero">You’ve built an income. Let’s make sense of its story.</span>
          </motion.h1>
          <motion.p variants={fadeUp} className="mt-5 max-w-xl text-sm leading-relaxed text-slate-600 sm:text-base">
            More than traditional credit history. Explore what 12 months of freelance earnings can tell you, with an AI copilot that explains, not decides.
          </motion.p>
          <motion.div variants={fadeUp} className="mt-7 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            <PayPalLoginButton onClick={onLogin} busy={busy} />
            <Button variant="ghost" className="border-paypal/20" onClick={enterDemo}>
              Tour the cockpit <span aria-hidden="true">→</span>
            </Button>
          </motion.div>
          {notice && (
            <motion.p variants={fadeUp} className="mt-4 max-w-md text-sm text-amber-700 dark:text-amber-glow">
              {notice}
            </motion.p>
          )}
          <motion.div variants={fadeUp} className="mt-6 flex items-start gap-3 text-xs text-slate-600">
            <span className="mt-2 h-px w-5 shrink-0 bg-amber-500" />
            <span>A demo, not a bank decision. No guaranteed lending access.</span>
          </motion.div>
        </div>
        <motion.div variants={fadeUp} className="relative min-w-0 rounded-[2rem] bg-[#eaf4fb] px-4 py-3 sm:px-8 lg:px-5">
          <FloatingCards />
        </motion.div>
      </motion.main>

      <motion.section
        variants={stagger}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, amount: 0.3 }}
        className="relative z-10 mx-auto grid w-full max-w-[1600px] gap-4 border-t border-[rgb(var(--line))] px-5 py-6 md:grid-cols-3 lg:px-10"
      >
        {steps.map((step) => (
          <motion.div key={step.n} variants={fadeUp}>
            <div className="flex gap-3 py-2">
              <p className="font-display text-xl text-paypal">{step.n}</p>
              <div>
                <h2 className="text-sm font-semibold">{step.title}</h2>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{step.copy}</p>
              </div>
            </div>
          </motion.div>
        ))}
      </motion.section>

      <footer className="relative z-10 flex flex-wrap justify-between gap-3 border-t border-[rgb(var(--line))] px-5 py-5 text-[10px] text-slate-500 lg:px-10">
        <span>PAYPILOT AI · A little clarity goes a long way.</span>
        <span>Synthetic financial information · No real money movement</span>
      </footer>
    </div>
  )
}
