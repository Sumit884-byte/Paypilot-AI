import { useEffect, useState } from 'react'
import { AgGridReact } from '@ag-grid-community/react'
import type { ColDef } from '@ag-grid-community/core'
import { GlassCard } from '../components/ui/GlassCard'
import { MetricCard, Notice, PageHeading, Icon, CountUp } from '../components/ui/Workspace'
import { apiRequest, money, type Persona } from '../lib/api'
import { useAuth } from '../context/AuthContext'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

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

type TransactionRow = {
  txn_id: string
  date: string
  type: string
  amount_inr: number
  category: string
  status: string
}

const demoNotice = 'Synthetic demo data · PayPal sandbox only · no real lending or money movement.'

function usePersona() {
  const [p, setP] = useState<Persona | null>(null)
  useEffect(() => {
    apiRequest<Persona>('/demo/persona/priya').then(setP).catch(() => {})
  }, [])
  return p
}

// Custom cell renderer for amount
function AmountCellRenderer({ value }: { value: any }) {
  return <span className="font-semibold text-navy-950 dark:text-white">{money(Number(value) || 0)}</span>
}

// Custom cell renderer for transaction type
function TypeCellRenderer({ value }: { value: any }) {
  const colors: Record<string, string> = {
    sale: 'text-emerald-600 dark:text-emerald-400',
    refund: 'text-rose-600 dark:text-rose-400',
    dispute: 'text-amber-600 dark:text-amber-400',
    expense: 'text-slate-600 dark:text-slate-400',
  }
  const icon: Record<string, string> = {
    sale: '$',
    refund: '↩',
    dispute: '⚠',
    expense: '–',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 ${colors[value] || colors.sale}`}>
      <span className="text-xs">{icon[value] || '•'}</span>
      <span className="capitalize">{String(value)}</span>
    </span>
  )
}

// Custom cell renderer for status
function StatusCellRenderer({ value }: { value: any }) {
  const isCompleted = String(value).toLowerCase() === 'completed' || String(value).toLowerCase() === 's'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${
        isCompleted
          ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'bg-amber-500/10 text-amber-700 dark:text-amber-300'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${isCompleted ? 'bg-emerald-500' : 'bg-amber-500'}`} />
      {String(value)}
    </span>
  )
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

  // AG Grid column definitions with PayScore theming
  const columnDefs: ColDef<TransactionRow>[] = [
    {
      headerName: 'Date',
      field: 'date',
      width: 120,
      cellClass: 'text-slate-600 dark:text-slate-300 text-sm',
      headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
    },
    {
      headerName: 'Type',
      field: 'type',
      width: 110,
      cellRenderer: TypeCellRenderer,
      headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
    },
    {
      headerName: 'Amount',
      field: 'amount_inr',
      width: 130,
      cellRenderer: AmountCellRenderer,
      headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
    },
    {
      headerName: 'Category',
      field: 'category',
      width: 140,
      cellClass: 'text-slate-600 dark:text-slate-300 text-sm capitalize',
      headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
    },
    {
      headerName: 'Status',
      field: 'status',
      width: 120,
      cellRenderer: StatusCellRenderer,
      headerClass: 'bg-paypal/5 text-paypal font-semibold text-xs uppercase tracking-wider',
    },
  ]

  // AG Grid theme - enhanced Paypilot theme matching design system
  useEffect(() => {
    // Inject theme CSS dynamically for better integration
    const styleId = 'paypilot-ag-grid-theme'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = `
        .paypilot-grid .ag-root-wrapper {
          border-radius: 16px !important;
          border: 1px solid rgb(0 112 186 / 0.16) !important;
          background: rgb(var(--surface) / 0.5) !important;
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
        }
        .paypilot-grid .ag-header {
          background: rgb(0 112 186 / 0.06) !important;
          border-bottom: 1px solid rgb(0 112 186 / 0.16) !important;
        }
        .paypilot-grid .ag-header-cell {
          color: #0070ba !important;
          font-weight: 700 !important;
          font-size: 10px !important;
          letter-spacing: 0.08em !important;
          text-transform: uppercase !important;
        }
        .paypilot-grid .ag-row:hover {
          background: rgb(0 112 186 / 0.05) !important;
        }
        .paypilot-grid .ag-row-odd {
          background: rgb(0 112 186 / 0.02) !important;
        }
        .paypilot-grid .ag-cell {
          border-right: 1px solid rgb(148 163 184 / 0.08) !important;
        }
        .paypilot-grid .ag-cell:last-child {
          border-right: none !important;
        }
        .paypilot-grid .ag-paging-panel {
          border-top: 1px solid rgb(0 112 186 / 0.12) !important;
        }
        .dark .paypilot-grid .ag-root-wrapper {
          border-color: rgb(255 255 255 / 0.1) !important;
          background: rgb(17 26 46 / 0.6) !important;
        }
        .dark .paypilot-grid .ag-header {
          background: rgb(0 112 186 / 0.1) !important;
          border-bottom-color: rgb(255 255 255 / 0.1) !important;
        }
        .dark .paypilot-grid .ag-header-cell {
          color: #009cde !important;
        }
        .dark .paypilot-grid .ag-row:hover {
          background: rgb(0 112 186 / 0.08) !important;
        }
        .dark .paypilot-grid .ag-row-odd {
          background: rgb(0 112 186 / 0.04) !important;
        }
        .dark .paypilot-grid .ag-cell {
          border-right-color: rgb(255 255 255 / 0.05) !important;
        }
        .dark .paypilot-grid .ag-paging-panel {
          border-top-color: rgb(255 255 255 / 0.1) !important;
        }
        .paypilot-grid .ag-row-animation {
          transition: background-color 0.2s ease;
        }
      `
      document.head.appendChild(style)
    }
    return () => {
      const style = document.getElementById(styleId)
      if (style) style.remove()
    }
  }, [])

  // Prepare transaction data for AG Grid
  const rowData: TransactionRow[] = Array.isArray(persona?.recent_transactions) ? persona.recent_transactions.map((t) => ({
    txn_id: t.txn_id,
    date: new Date(t.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: '2-digit' }),
    type: t.type,
    amount_inr: Number(t.amount_inr) || 0,
    category: t.category,
    status: t.status,
  })) : []

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Income profile"
        title="Your work, in a clearer light."
        detail="A 12-month view of payment consistency and client activity."
      />
      <Notice>
        {profile?.source === 'paypal'
          ? 'Linked PayPal profile · aggregates only; transaction feed is not exposed by this endpoint.'
          : demoNotice}
      </Notice>
      {error && <Notice tone="warning">{error} · Start the API to load data.</Notice>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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
              detail={`Longest gap · ${profile.longest_income_gap_days_12m} days`}
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
                <AreaChart data={profile.monthly_income_12m}>
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

      {/* AG Grid Transaction Feed */}
      <GlassCard className="overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-slate-200/60 dark:border-white/10 p-5">
          <div>
            <h2 className="font-semibold">Transaction feed</h2>
            <p className="mt-1 text-xs text-slate-500">Last 12 months · AG Grid powered</p>
          </div>
          <span className="rounded-full bg-paypal/10 px-3 py-1 text-[11px] font-semibold text-paypal">
            {rowData.length} transactions
          </span>
        </div>
        <div className="ag-theme-quartz paypilot-grid" style={{ height: 400 }}>
          <AgGridReact
            columnDefs={columnDefs}
            rowData={rowData}
            domLayout="autoHeight"
            defaultColDef={{
              resizable: true,
              sortable: true,
              filter: true,
            }}
            rowStyle={{
              backgroundColor: 'transparent',
              fontFamily: 'Plus Jakarta Sans, Inter, system-ui, sans-serif',
            }}
          />
        </div>
      </GlassCard>
    </div>
  )
}
