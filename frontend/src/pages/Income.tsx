import { lazy, Suspense, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { MetricCard, Notice, PageHeading, Icon, CountUp } from '../components/ui/Workspace'
import type { TransactionRow } from '../components/income/TransactionGrid'
import { apiRequest, fromFirstIncome, money, monthLabel, type Persona } from '../lib/api'
import { useActivePersona } from '../lib/personas'
import { useAuth } from '../context/AuthContext'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

// AG Grid is the largest dependency in the app, so it loads only with this feed
const TransactionGrid = lazy(() => import('../components/income/TransactionGrid'))

type Profile = {
  total_income_12m_inr: number
  monthly_income_12m: Array<{ month: string; income_inr: number }>
  distinct_client_count_12m: number
  refund_rate_12m: number
  dispute_rate_12m: number
  longest_income_gap_days_12m: number
  income_trend_12m: string
  source: string
}

const demoNotice = 'Synthetic demo data · PayPal sandbox only · no real lending or money movement.'

function usePersona() {
  const { key, linked } = useActivePersona()
  const [p, setP] = useState<Persona | null>(null)
  useEffect(() => {
    // A linked account never loads a demo persona, so its transactions cannot appear here
    if (!linked) apiRequest<Persona>(`/demo/persona/${key}`).then(setP).catch(() => {})
  }, [key, linked])
  return p
}

export function Income() {
  const { session } = useAuth()
  const [profile, setProfile] = useState<Profile | null>(null)
  const persona = usePersona()
  const [error, setError] = useState('')

  useEffect(() => {
    apiRequest<Profile>(`/income-profile?persona=${session?.persona ?? 'priya'}`)
      .then(setProfile)
      .catch((e) => setError(e.message))
  }, [session?.persona])

  // Prepare transaction data for AG Grid
  const rowData: TransactionRow[] = Array.isArray(persona?.recent_transactions) ? persona.recent_transactions.map((t) => ({
    txn_id: t.txn_id,
    date: t.date,
    type: t.type,
    amount_inr: Number(t.amount_inr) || 0,
    category: t.category,
    status: t.status,
  })) : []

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Income profile"
        title="Income, beyond the balance."
        detail="A 12-month view of payment consistency and client activity."
      />
      <Notice>
        {profile?.source === 'paypal'
          ? 'Linked PayPal profile · aggregates only; transaction feed is not exposed by this endpoint.'
          : demoNotice}
      </Notice>
      {error && <Notice tone="warning">{error} · Start the API to load data.</Notice>}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        {profile ? (
          <>
            <MetricCard
              label="Income · 12 months"
              value={<CountUp to={profile.total_income_12m_inr} decimals={0} prefix="₹" />}
              detail={`${profile.income_trend_12m} direction`}
              icon={<Icon name="income" />}
              delay={0.05}
            />
            <MetricCard
              label="Distinct clients"
              value={<CountUp to={profile.distinct_client_count_12m} />}
              detail="12-month buyer count"
              icon={<Icon name="users" />}
              tone="gold"
              delay={0.1}
            />
            <MetricCard
              label="Refund rate"
              value={`${(profile.refund_rate_12m * 100).toFixed(1)}%`}
              detail="Share of transactions"
              icon={<Icon name="arrow" />}
              tone="green"
              delay={0.15}
            />
            <MetricCard
              label="Dispute rate"
              value={`${(profile.dispute_rate_12m * 100).toFixed(1)}%`}
              detail="Share of transactions"
              icon={<Icon name="clock" />}
              tone="rose"
              delay={0.2}
            />
          </>
        ) : null}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <GlassCard>
          <h2 className="font-semibold">Monthly income</h2>
          <p className="mb-5 mt-1 text-xs text-slate-500">INR · trailing 12 months</p>
          {profile?.monthly_income_12m?.length ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={fromFirstIncome(profile.monthly_income_12m)}>
                  <defs>
                    <linearGradient id="incomeGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#0070BA" stopOpacity="0.35" />
                      <stop offset="100%" stopColor="#0070BA" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="month"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 11, fill: 'rgb(71 85 105)' }}
                    tickFormatter={monthLabel}
                    interval="preserveStartEnd"
                    minTickGap={18}
                  />
                  <YAxis hide />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgb(17 26 46)',
                      border: '1px solid rgb(0 112 186)',
                      borderRadius: '12px',
                      color: 'white',
                    }}
                    formatter={(value: any) => [money(value), 'Income']}
                  />
                  <Area
                    type="monotone"
                    dataKey="income_inr"
                    stroke="#0070BA"
                    strokeWidth={2}
                    fill="url(#incomeGradient)"
                    animationDuration={1200}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-16 text-center text-sm text-slate-500">Waiting for income data…</p>
          )}
        </GlassCard>

        <GlassCard>
          <h2 className="font-semibold">Payment rhythm</h2>
          <div className="mt-6 space-y-4">
            <div className="rounded-2xl bg-paypal/5 p-4">
              <p className="text-xs text-slate-500">Monthly direction</p>
              <p className="mt-2 text-lg font-semibold capitalize">{profile?.income_trend_12m}</p>
            </div>
            <div className="rounded-2xl bg-amber-400/10 p-4">
              <p className="text-xs text-slate-500">Longest income gap</p>
              <p className="mt-2 text-lg font-semibold">{profile?.longest_income_gap_days_12m} days</p>
            </div>
            <div className="rounded-2xl bg-emerald-500/10 p-4">
              <p className="text-xs text-slate-500">Client retention</p>
              <p className="mt-2 text-lg font-semibold">{profile?.distinct_client_count_12m} active buyers</p>
            </div>
          </div>
        </GlassCard>
      </div>

      <GlassCard>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold">Income Passport</h2>
            <p className="mt-1 text-sm text-slate-500">
              Generate a one-page shareable summary with a public verification link. Aggregates only — no raw statements.
            </p>
          </div>
          <Link to="/app/passport"><Button>Open passport</Button></Link>
        </div>
      </GlassCard>

      {/* AG Grid Transaction Feed: demo personas only; the linked profile returns aggregates, not rows */}
      {rowData.length > 0 && <GlassCard className="overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-slate-200/60 dark:border-white/10 p-5">
          <div>
            <h2 className="font-semibold">Transaction feed</h2>
            <p className="mt-1 text-xs text-slate-500">Most recent transactions · AG Grid powered</p>
          </div>
          <span className="rounded-full bg-paypal/10 px-3 py-1 text-[11px] font-semibold text-paypal">
            {rowData.length} transactions
          </span>
        </div>
        <Suspense fallback={<p className="py-16 text-center text-sm text-slate-500">Loading transactions…</p>}>
          <TransactionGrid rows={rowData} />
        </Suspense>
      </GlassCard>}
    </div>
  )
}
