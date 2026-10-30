import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Notice, PageHeading, Icon } from '../components/ui/Workspace'
import { Skeleton } from '../components/ui/Skeleton'
import { apiRequest, money, type Persona } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

type IncomeProfile = {
  total_income_12m_inr: number
  monthly_income_12m?: Array<{ month: string; income_inr: number }>
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
  const { session } = useAuth()
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
    <div className="space-y-6">
      <PageHeading eyebrow="Your financial workspace" title={`Good morning${persona ? `, ${persona.display_name.split(' ')[0]}` : ''}.`}
        detail="Your work has a rhythm. Here’s the bigger picture, and a little help with what comes next." action={
          <Link to="/app/copilot"><Button><span>Continue with copilot</span><Icon name="arrow" size={16} /></Button></Link>
        } />

      {error && <Notice tone="warning">{error} · Start the API to load live demo data. The demo tour remains available below.</Notice>}
      {session?.demo && <Notice>Demo workspace · synthetic persona data only. No real credit decision, lending, or money movement.</Notice>}

      <div className="grid gap-4 border-y border-[rgb(var(--line))] py-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: '12-month income', value: profile ? money(profile.total_income_12m_inr, true) : '—', detail: 'Monthly average' },
          { label: 'Distinct clients', value: profile?.distinct_client_count_12m ?? '—', detail: 'Across the trailing year' },
          { label: 'Refund rate', value: profile ? `${(profile.refund_rate_12m * 100).toFixed(1)}%` : '—', detail: 'Share of total receipts' },
          { label: 'Longest payment gap', value: profile ? `${profile.longest_income_gap_days_12m} days` : '—', detail: 'Across earning months' },
        ].map((item) => (
          <div key={item.label} className="px-1 py-1">
            <p className="text-xs text-slate-500">{item.label}</p>
            <p className="mt-2 text-2xl font-bold text-[rgb(var(--ink))]">{item.value}</p>
            <p className="mt-1 text-[11px] text-slate-500">{item.detail}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.65fr_.7fr]">
        <GlassCard interactive={false} className="min-w-0 p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold">Your income is finding its stride.</h2>
              <p className="mt-1 text-xs text-slate-500">12 months of synthetic cashflow</p>
            </div>
            <span className="hidden text-[10px] uppercase text-slate-500 sm:block">Trailing 12 months</span>
          </div>
          {profile ? (
            <>
              <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
                <p className="text-3xl font-bold">{money(profile.monthly_income_12m?.at(-1)?.income_inr ?? profile.total_income_12m_inr / 12, true)}</p>
                <span className="rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold text-emerald-800">{profile.income_trend_12m}</span>
              </div>
              {profile.monthly_income_12m?.length ? (
                <div className="mt-3 h-56 min-w-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={profile.monthly_income_12m}>
                      <defs><linearGradient id="overview-income" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0070BA" stopOpacity="0.2" /><stop offset="100%" stopColor="#0070BA" stopOpacity="0" /></linearGradient></defs>
                      <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#718096' }} />
                      <YAxis hide />
                      <Tooltip formatter={(value) => [money(Number(value)), 'Income']} />
                      <Area type="monotone" dataKey="income_inr" stroke="#0070BA" strokeWidth={2} fill="url(#overview-income)" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : <p className="py-16 text-center text-sm text-slate-500">Income trend is not available.</p>}
              <Link to="/app/income" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-paypal">Explore the transactions <Icon name="arrow" size={13} /></Link>
            </>
          ) : <div className="grid h-64 place-items-center text-center text-sm text-slate-500">{error ? 'Start the API to load the synthetic income profile.' : <Skeleton className="h-40 w-full" />}</div>}
        </GlassCard>

        <GlassCard interactive={false} className="bg-[#eaf4fb] p-5 sm:p-6">
          <p className="text-[10px] font-semibold uppercase text-paypal">Paypilot guide</p>
          <h2 className="mt-2 font-display text-2xl">A good place to begin.</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-500">Let’s look at the facts before making a next move.</p>
          <div className="mt-5 space-y-3 text-xs">
            <div className="flex justify-between gap-3"><span className="text-slate-500">PayScore</span><Link to="/app/score" className="font-semibold text-paypal">Review signals ↗</Link></div>
            <div className="flex justify-between gap-3"><span className="text-slate-500">Offer guard</span><Link to="/app/offer-guard" className="font-semibold text-paypal">Review an offer ↗</Link></div>
          </div>
          <p className="mt-4 text-[11px] leading-relaxed text-slate-500">Your approval is always required. This is an estimate, not a lending decision.</p>
          <Link to="/app/copilot" className="mt-4 inline-flex"><Button>Ask the copilot</Button></Link>
        </GlassCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-[.9fr_1.5fr]">
        <section>
          <h2 className="mb-2 font-display text-2xl">Make the numbers useful.</h2>
          {[
            { title: 'Income', detail: '12 months, clients, one clear picture.', href: '/app/income' },
            { title: 'PayScore', detail: 'Understand what shapes your demo score.', href: '/app/score' },
            { title: 'Offer guard', detail: 'Look beyond the advertised rate.', href: '/app/offer-guard' },
          ].map((item) => <Link key={item.href} to={item.href} className="flex items-center justify-between gap-4 border-b border-[rgb(var(--line))] py-3">
            <span><span className="block text-sm font-semibold">{item.title}</span><span className="mt-1 block text-xs text-slate-500">{item.detail}</span></span>
            <Icon name="arrow" size={15} className="shrink-0 text-paypal" />
          </Link>)}
        </section>

        <GlassCard interactive={false} className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-3">
            <h2 className="text-sm font-semibold">Your three-minute demo path</h2>
            <span className="text-[10px] uppercase text-slate-500">{completed.size} of {DEMO_STEPS.length} visited</span>
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
          
          <p className="mt-4 text-xs leading-relaxed">Next: explore income, then check whether an illustrative amount fits your cashflow.</p>
          <p className="mt-4 text-[10px] text-slate-500">Synthetic demo data only. No real credit decision or money movement.</p>
        </GlassCard>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200/50 px-4 py-3 text-[11px] text-slate-500 dark:border-white/10">
        <span>{profile?.source === 'paypal' ? 'PayPal sandbox account linked' : 'Persona data is synthetic and labelled'}</span>
        <span>PayScore assists with review; it does not approve real credit.</span>
      </div>
    </div>
  )
}
