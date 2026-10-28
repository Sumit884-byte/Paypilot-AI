import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Notice, PageHeading, MetricCard, Icon, PulseDot } from '../components/ui/Workspace'
import { Skeleton } from '../components/ui/Skeleton'
import { apiRequest, money, type Persona } from '../lib/api'
import { useAuth } from '../context/AuthContext'

type IncomeProfile = {
  total_income_12m_inr: number
  distinct_client_count_12m: number
  refund_rate_12m: number
  dispute_rate_12m: number
  income_trend_12m: string
  longest_income_gap_days_12m: number
  source: string
}

const DEMO_STEPS = [
  { id: 'income', label: 'Income profile', href: '/app/income', icon: 'income' },
  { id: 'score', label: 'Explainable score', href: '/app/score', icon: 'spark' },
  { id: 'offer', label: 'Offer guard', href: '/app/offer-guard', icon: 'shield' },
  { id: 'copilot', label: 'AI copilot', href: '/app/copilot', icon: 'chat' },
  { id: 'repay', label: 'Repayment', href: '/app/repay', icon: 'clock' },
]

function useDemoProgress() {
  const [completed, setCompleted] = useState<Set<string>>(new Set())
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem('paypilot.demo_progress')
      if (stored) setCompleted(new Set(JSON.parse(stored)))
    } catch {}
  }, [])
  const mark = (id: string) => {
    setCompleted((prev) => {
      const next = new Set(prev)
      next.add(id)
      sessionStorage.setItem('paypilot.demo_progress', JSON.stringify([...next]))
      return next
    })
  }
  return { completed, mark }
}

export function Overview() {
  const { session, enterDemo } = useAuth()
  const location = useLocation()
  const [profile, setProfile] = useState<IncomeProfile | null>(null)
  const [persona, setPersona] = useState<Persona | null>(null)
  const [error, setError] = useState('')
  const name = session?.persona ?? 'priya'
  const { completed, mark } = useDemoProgress()

  // Mark current page as completed in demo flow
  useEffect(() => {
    const current = DEMO_STEPS.find((s) => location.pathname === s.href)
    if (current) mark(current.id)
  }, [location.pathname, mark])

  useEffect(() => {
    let active = true
    Promise.all([
      apiRequest<IncomeProfile>(`/income-profile?persona=${name}`),
      apiRequest<Persona>(`/demo/persona/${name}`),
    ]).then(([income, demo]) => {
      if (!active) return
      setProfile(income)
      setPersona(demo)
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : 'Could not load the demo profile.')
    })
    return () => { active = false }
  }, [name])

  return (
    <div className="space-y-7">
      <PageHeading eyebrow="Your financial workspace" title={`Good morning${persona ? `, ${persona.display_name.split(' ')[0]}` : ''}.`}
        detail="A clearer view of the income behind your next move." action={
          <Link to="/app/score"><Button><span>Run PayScore</span><Icon name="arrow" size={16} /></Button></Link>
        } />

      {error && <Notice tone="warning">{error} · Start the API to load live demo data. The demo tour remains available below.</Notice>}
      {session?.demo && <Notice>Demo workspace · synthetic persona data only. No real credit decision, lending, or money movement.</Notice>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {profile ? <>
          <MetricCard label="Income · 12 months" value={money(profile.total_income_12m_inr, true)} detail={`${profile.income_trend_12m} monthly direction`} icon={<Icon name="income" />} delay={0.05} />
          <MetricCard label="Distinct clients" value={profile.distinct_client_count_12m} detail="12-month buyer count" icon={<Icon name="users" />} tone="gold" delay={0.1} />
          <MetricCard label="Refund rate" value={`${(profile.refund_rate_12m * 100).toFixed(1)}%`} detail="Share of completed sales" icon={<Icon name="arrow" />} tone="green" delay={0.15} />
          <MetricCard label="Longest payment gap" value={`${profile.longest_income_gap_days_12m} days`} detail={`Dispute rate ${(profile.dispute_rate_12m * 100).toFixed(1)}%`} icon={<Icon name="clock" />} tone="rose" delay={0.2} />
        </> : [1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-36 rounded-3xl" />)}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.45fr_.85fr]">
        <GlassCard interactive={false} className="overflow-hidden p-0">
          <div className="flex items-center justify-between p-5 sm:p-6">
            <div><p className="text-sm font-semibold">Your PayScore workspace</p><p className="mt-1 text-xs text-slate-500">One connected story, from income to repayment.</p></div>
            <span className="flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[11px] font-semibold text-emerald-600 dark:text-emerald-300"><PulseDot /> API ready</span>
          </div>
          <div className="grid border-t border-slate-200/60 dark:border-white/10 sm:grid-cols-3">
            {[
              { title: 'Income profile', detail: '12 months of cashflow', href: '/app/income', icon: 'income' },
              { title: 'Explainable score', detail: 'Understand the signals', href: '/app/score', icon: 'spark' },
              { title: 'Offer guard', detail: 'See the cost behind APR', href: '/app/offer-guard', icon: 'shield' },
            ].map((item, index) => <motion.div key={item.href} whileHover={{ backgroundColor: 'rgba(0,112,186,.055)' }} className={`border-slate-200/60 p-5 dark:border-white/10 ${index ? 'border-t sm:border-l sm:border-t-0' : ''}`}>
              <Link to={item.href} className="block rounded-xl focus-visible:outline">
                <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-2xl bg-paypal/10 text-paypal"><Icon name={item.icon} /></span>
                <p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs text-slate-500">{item.detail}</p>
                <span className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-paypal">Open <Icon name="arrow" size={14} /></span>
              </Link>
            </motion.div>)}
          </div>
        </GlassCard>

        <GlassCard interactive={false} className="relative overflow-hidden p-6">
          <div className="absolute -right-12 -top-14 h-40 w-40 rounded-full bg-amber-400/15 blur-3xl" />
          <p className="relative text-[11px] font-bold uppercase tracking-[.2em] text-amber-600 dark:text-amber-300">3-minute demo flow</p>
          <h2 className="relative mt-3 font-display text-2xl font-bold">Follow Priya's story</h2>
          <p className="relative mt-2 text-sm leading-relaxed text-slate-500 dark:text-slate-400">Income → score → inspect an offer → ask the copilot → simulate a sandbox payout → track the first repayment.</p>
          <div className="relative mt-5 flex flex-wrap gap-2">
            <Button onClick={enterDemo}><Icon name="spark" size={16} /> Start demo</Button>
            <Link to="/app/copilot"><Button variant="ghost">Ask the copilot</Button></Link>
          </div>
          
          {/* Demo Progress Tracker */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="mt-6"
          >
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Progress</p>
              <p className="text-xs font-mono text-paypal">{completed.size} / {DEMO_STEPS.length} steps</p>
            </div>
            <div className="mt-3 flex items-center gap-2 overflow-x-auto pb-2">
              {DEMO_STEPS.map((step, i) => (
                <motion.div
                  key={step.id}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.05 * i, type: 'spring', stiffness: 200, damping: 20 }}
                  className="flex flex-col items-center gap-1.5 flex-shrink-0"
                >
                  <Link to={step.href} className="relative">
                    <span
                      className={`flex h-10 w-10 items-center justify-center rounded-xl transition-all ${
                        completed.has(step.id)
                          ? 'bg-emerald-500 text-white shadow-[0_0_12px_rgba(16,185,129,0.4)]'
                          : location.pathname === step.href
                          ? 'bg-paypal text-white shadow-glow'
                          : 'bg-slate-100 text-slate-400 dark:bg-white/10 dark:text-slate-500'
                      }`}
                    >
                      {completed.has(step.id) ? (
                        <Icon name="check" size={16} className="text-white" />
                      ) : (
                        <Icon name={step.icon} size={16} />
                      )}
                    </span>
                    {completed.has(step.id) && (
                      <motion.span
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[9px] text-white"
                      >
                        ✓
                      </motion.span>
                    )}
                  </Link>
                  <span className="text-[10px] font-medium text-center whitespace-nowrap text-slate-600 dark:text-slate-400">
                    {step.label}
                  </span>
                  {i < DEMO_STEPS.length - 1 && (
                    <span className={`h-0.5 w-12 ${completed.has(DEMO_STEPS[i + 1].id) ? 'bg-emerald-500' : 'bg-slate-200 dark:bg-white/10'}`} />
                  )}
                </motion.div>
              ))}
            </div>
          </motion.div>
          
          <p className="relative mt-5 text-[10px] uppercase tracking-[.14em] text-slate-500">{persona?.scenario?.headline ?? 'Synthetic persona · PayPal sandbox only'}</p>
        </GlassCard>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/50 px-4 py-3 text-[11px] text-slate-500 dark:border-white/10">
        <span>{profile?.source === 'paypal' ? 'PayPal sandbox account linked' : 'Persona data is synthetic and labelled'}</span>
        <span>PayScore assists with review; it does not approve real credit.</span>
      </div>
    </div>
  )
}
