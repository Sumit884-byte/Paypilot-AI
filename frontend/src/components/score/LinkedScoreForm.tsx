import { useState, type FormEvent, type ReactNode } from 'react'
import { GlassCard } from '../ui/GlassCard'
import { Button } from '../ui/Button'
import { inputClass } from '../ui/Workspace'

export type LinkedDetails = {
  age_years: number
  employment_type: string
  requested_loan_amount_inr: number
  requested_term_months: number
  monthly_income_inr?: number
  business_age_months?: number
  existing_monthly_debt_payments_inr?: number
  prior_defaults_count?: number
}

export type ScoreInput = { field: string; value: number | string | null; source: 'paypal' | 'you' | 'not_available' }

const DETAILS_KEY = 'paypilot.linked_details'

const EMPLOYMENT = [
  ['self_employed', 'Self-employed / seller'],
  ['freelancer', 'Freelancer'],
  ['salaried', 'Salaried'],
  ['business_owner', 'Business owner'],
  ['other', 'Other'],
] as const

const LABELS: Record<string, string> = {
  monthly_income_inr: 'Monthly income',
  avg_monthly_revenue_inr: 'Average monthly revenue (6 months)',
  revenue_volatility_cv: 'Revenue volatility',
  txn_count_90d: 'Sales in the last 90 days',
  avg_txn_value_inr: 'Average sale (90 days)',
  active_months_12m: 'Months with income (of 12)',
  refund_rate_90d: 'Refund rate (90 days)',
  dispute_rate_12m: 'Dispute rate (12 months)',
  avg_client_turnaround_days: 'Invoice turnaround (days)',
  top_client_revenue_share: 'Largest client share',
  age_years: 'Age',
  employment_type: 'Employment',
  business_age_months: 'Business age (months)',
  existing_monthly_debt_payments_inr: 'Existing monthly repayments',
  prior_defaults_count: 'Past defaults',
  requested_loan_amount_inr: 'Loan requested',
  requested_term_months: 'Term (months)',
  avg_monthly_expenses_inr: 'Average monthly expenses',
  late_payment_rate_90d: 'Late payment rate',
}

function saved(): Partial<Record<keyof LinkedDetails, string>> {
  try {
    return JSON.parse(sessionStorage.getItem(DETAILS_KEY) || '{}')
  } catch {
    return {}
  }
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-xs font-semibold">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-slate-500">{hint}</span>}
    </label>
  )
}

/** The facts PayPal does not share with Paypilot. Everything about sales comes from the linked account. */
export function LinkedScoreForm({ busy, onSubmit }: { busy: boolean; onSubmit: (details: LinkedDetails) => void }) {
  const [form, setForm] = useState(() => ({
    age_years: '', employment_type: 'self_employed', requested_loan_amount_inr: '100000', requested_term_months: '12',
    monthly_income_inr: '', business_age_months: '', existing_monthly_debt_payments_inr: '', prior_defaults_count: '',
    ...saved(),
  }))
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const ready = Number(form.age_years) >= 18 && Number(form.requested_loan_amount_inr) > 0 && Number(form.requested_term_months) >= 1

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!ready) return
    try { sessionStorage.setItem(DETAILS_KEY, JSON.stringify(form)) } catch {}
    const optional = (value: string) => (value.trim() === '' ? undefined : Number(value))
    onSubmit({
      age_years: Number(form.age_years),
      employment_type: form.employment_type,
      requested_loan_amount_inr: Number(form.requested_loan_amount_inr),
      requested_term_months: Number(form.requested_term_months),
      monthly_income_inr: optional(form.monthly_income_inr),
      business_age_months: optional(form.business_age_months),
      existing_monthly_debt_payments_inr: optional(form.existing_monthly_debt_payments_inr),
      prior_defaults_count: optional(form.prior_defaults_count),
    })
  }

  const number = { type: 'number', inputMode: 'numeric' as const, min: 0, className: inputClass }
  return (
    <GlassCard interactive={false}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <h2 className="font-semibold">A few details PayPal doesn't share</h2>
          <p className="mt-1 text-xs text-slate-500">
            Sales, refunds, disputes and income history come from your linked PayPal account. These stay in this browser
            and are sent only to score you.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Age"><input {...number} min={18} max={100} required value={form.age_years} onChange={set('age_years')} /></Field>
          <Field label="Employment">
            <select className={inputClass} value={form.employment_type} onChange={set('employment_type')}>
              {EMPLOYMENT.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </Field>
          <Field label="Loan amount (₹)"><input {...number} min={1} required value={form.requested_loan_amount_inr} onChange={set('requested_loan_amount_inr')} /></Field>
          <Field label="Term (months)"><input {...number} min={1} max={360} required value={form.requested_term_months} onChange={set('requested_term_months')} /></Field>
          <Field label="Monthly income (₹)" hint="Optional. Empty uses your PayPal average.">
            <input {...number} value={form.monthly_income_inr} onChange={set('monthly_income_inr')} placeholder="From PayPal" />
          </Field>
          <Field label="Existing repayments / month (₹)" hint="Optional">
            <input {...number} value={form.existing_monthly_debt_payments_inr} onChange={set('existing_monthly_debt_payments_inr')} />
          </Field>
          <Field label="Business age (months)" hint="Optional">
            <input {...number} max={1200} value={form.business_age_months} onChange={set('business_age_months')} />
          </Field>
          <Field label="Past loan defaults" hint="Optional">
            <input {...number} max={50} value={form.prior_defaults_count} onChange={set('prior_defaults_count')} />
          </Field>
        </div>
        <Button type="submit" disabled={!ready || busy}>{busy ? 'Scoring…' : 'Run PayScore'}</Button>
      </form>
    </GlassCard>
  )
}

const fmt = (row: ScoreInput) => {
  if (row.value === null || row.value === undefined) return '—'
  if (typeof row.value === 'string') return row.value.replaceAll('_', ' ')
  if (row.field.endsWith('_inr')) return `₹${Math.round(row.value).toLocaleString('en-IN')}`
  if (row.field.includes('rate') || row.field === 'top_client_revenue_share') return `${(row.value * 100).toFixed(1)}%`
  return String(row.value)
}

/** Where every model input came from, so a linked score never hides a borrowed figure. */
export function ScoreInputs({ inputs }: { inputs: ScoreInput[] }) {
  const groups: Array<[ScoreInput['source'], string]> = [
    ['paypal', 'From your PayPal account'], ['you', 'From you'], ['not_available', 'Not available (left blank for the model)'],
  ]
  return (
    <GlassCard interactive={false}>
      <h2 className="font-semibold">What this score used</h2>
      <div className="mt-4 grid gap-5 md:grid-cols-3">
        {groups.map(([source, title]) => {
          const rows = inputs.filter((row) => row.source === source)
          if (!rows.length) return null
          return (
            <div key={source}>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{title}</p>
              <dl className="mt-2 space-y-1.5 text-sm">
                {rows.map((row) => (
                  <div key={row.field} className="flex justify-between gap-3">
                    <dt className="text-slate-600 dark:text-slate-300">{LABELS[row.field] ?? row.field}</dt>
                    <dd className="font-medium tabular-nums">{fmt(row)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}
