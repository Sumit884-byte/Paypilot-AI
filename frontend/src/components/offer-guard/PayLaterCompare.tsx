import { useState } from 'react'
import { motion } from 'framer-motion'
import { GlassCard } from '../ui/GlassCard'
import { Button } from '../ui/Button'
import { Field, inputClass, Notice } from '../ui/Workspace'
import { postJson } from '../../lib/api'

export type OfferTerms = {
  advertised_apr_pct: number
  processing_fee_pct: number
  principal: number
  term_months: number
  lender_name: string
}

type PayLaterOption = {
  id: string
  name: string
  provider: string
  eligible: boolean
  ineligible_reason: string | null
  payments: number
  interval: string
  term_note?: string | null
  instalment: number | null
  instalment_best?: number
  effective_annual_pct: number | null
  effective_annual_pct_best?: number
  apr_basis: string
  cost_of_credit?: number
  cost_of_credit_best?: number
}

type PayLaterResult = {
  market: string
  currency: string | null
  pay_later_availability: 'modelled' | 'not_modelled' | 'unavailable'
  availability_note: string
  options: PayLaterOption[]
  cheapest: { id: string; name: string; cost_of_credit: number; saving_vs_offer: number | null } | null
  summary: string | null
  ranking_basis: string
  terms_source: { url: string; retrieved: string }
  disclaimer: string
}

const MARKETS = [
  { code: 'IN', label: 'India · INR', defaultAmount: (terms: OfferTerms) => terms.principal },
  { code: 'US', label: 'United States · USD (illustration)', defaultAmount: () => 1200 },
] as const

function amount(value: number | null | undefined, currency: string | null) {
  if (value == null) return '—'
  return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
    style: 'currency',
    currency: currency ?? 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

export function PayLaterCompare({ terms }: { terms: OfferTerms }) {
  const [market, setMarket] = useState<'IN' | 'US'>('IN')
  const [purchase, setPurchase] = useState(String(terms.principal))
  const [result, setResult] = useState<PayLaterResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function chooseMarket(code: 'IN' | 'US') {
    setMarket(code)
    setPurchase(String(MARKETS.find((m) => m.code === code)!.defaultAmount(terms)))
    setResult(null)
  }

  async function compare() {
    setBusy(true)
    setError('')
    try {
      setResult(await postJson<PayLaterResult>('/offer-guard/pay-later', {
        purchase_amount: Number(purchase),
        market,
        advertised_apr_pct: terms.advertised_apr_pct,
        processing_fee_pct: terms.processing_fee_pct,
        term_months: terms.term_months,
        lender_name: terms.lender_name,
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Comparison unavailable')
    } finally {
      setBusy(false)
    }
  }

  return (
    <GlassCard>
      <h2 className="font-semibold">Is PayPal Pay Later cheaper?</h2>
      <p className="mt-1 text-xs text-slate-500">
        Prices this purchase with the offer above ({terms.advertised_apr_pct}% APR, {terms.processing_fee_pct}% fee,{' '}
        {terms.term_months} months) and with PayPal Pay Later, then ranks them by cost of credit.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <Field label="Buyer market">
          <select value={market} onChange={(e) => chooseMarket(e.target.value as 'IN' | 'US')} className={inputClass}>
            {MARKETS.map((m) => <option key={m.code} value={m.code}>{m.label}</option>)}
          </select>
        </Field>
        <Field label={`Purchase amount (${market === 'IN' ? 'INR' : 'USD'})`}>
          <input type="number" min="1" value={purchase} onChange={(e) => setPurchase(e.target.value)} className={inputClass} />
        </Field>
        <Button onClick={compare} disabled={busy || !(Number(purchase) > 0)}>
          {busy ? 'Comparing…' : 'Compare'}
        </Button>
      </div>

      {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}

      {result && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-5 space-y-4">
          {result.pay_later_availability !== 'modelled' && <Notice tone="warning">{result.availability_note}</Notice>}
          {result.summary && (
            <p className="rounded-2xl bg-emerald-500/10 p-4 text-sm font-semibold text-emerald-800 dark:text-emerald-300">{result.summary}</p>
          )}

          <div className="grid gap-3 md:grid-cols-3">
            {result.options.map((o) => {
              const cheapest = result.cheapest?.id === o.id
              return (
                <div
                  key={o.id}
                  className={`rounded-2xl border p-4 ${
                    !o.eligible
                      ? 'border-slate-200/60 opacity-60 dark:border-white/10'
                      : cheapest
                        ? 'border-emerald-500/40 bg-emerald-500/5'
                        : 'border-slate-200/60 dark:border-white/10'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold">{o.name}</p>
                    {cheapest && <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-bold uppercase text-white">Cheapest</span>}
                  </div>
                  <p className="text-[11px] text-slate-500">{o.provider}</p>
                  {o.eligible ? (
                    <dl className="mt-3 space-y-1.5 text-sm">
                      <div className="flex justify-between gap-2"><dt className="text-slate-500">Payments</dt><dd>{o.payments} × {amount(o.instalment, result.currency)}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-slate-500">Schedule</dt><dd className="text-right">{o.interval}</dd></div>
                      <div className="flex justify-between gap-2"><dt className="text-slate-500">Effective annual cost</dt><dd>{o.effective_annual_pct}%</dd></div>
                      <div className="flex justify-between gap-2 font-semibold"><dt>Cost of credit</dt><dd>{amount(o.cost_of_credit, result.currency)}</dd></div>
                      {o.cost_of_credit_best != null && o.cost_of_credit_best !== o.cost_of_credit && (
                        <p className="text-[11px] text-slate-500">
                          As low as {amount(o.cost_of_credit_best, result.currency)} ({o.effective_annual_pct_best}%) with the best APR.
                        </p>
                      )}
                      <p className="pt-1 text-[11px] text-slate-500">{o.apr_basis}</p>
                      {o.term_note && <p className="text-[11px] text-slate-500">{o.term_note}</p>}
                    </dl>
                  ) : (
                    <p className="mt-3 text-sm text-slate-500">{o.ineligible_reason}</p>
                  )}
                </div>
              )
            })}
          </div>

          <p className="text-[11px] text-slate-500">
            {result.ranking_basis} Terms: <a href={result.terms_source.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">PayPal Pay Later (US)</a>, checked {result.terms_source.retrieved}. {result.disclaimer}
          </p>
        </motion.div>
      )}
    </GlassCard>
  )
}
