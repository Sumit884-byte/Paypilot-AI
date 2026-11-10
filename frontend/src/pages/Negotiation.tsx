import { useState } from 'react'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Notice, PageHeading, MetricCard, Icon } from '../components/ui/Workspace'
import { money, postJson } from '../lib/api'

const APPLICANT_ID = 'PSC-PRIYA-001'

type Proposal = {
  agent?: string
  label?: string
  repayment_amount_inr: number
  term_months: number
  monthly_installment_inr: number
  revenue_share_pct: number
  payment_holiday_months: number
  annual_interest_rate_pct?: number
  reasons?: string[]
  simulated?: boolean
}

type Session = {
  session_id: string
  status: string
  round: number
  max_rounds: number
  evidence: {
    average_monthly_income_inr: number
    total_income_12m_inr: number
    classification: string
    refund_rate_12m?: number
    dispute_rate_12m?: number
    note?: string
  }
  current_proposal: Proposal | null
  latest_borrower?: {
    decision: string
    concerns?: string[]
    counteroffer?: Proposal | null
  }
  history: Array<{ at: string; round: number; event: string; payload: Record<string, unknown> }>
  outcome?: string | null
  settlement?: { mode: string; paypal_payout: boolean; message: string; terms?: Proposal }
  simulation_banner: string
}

export function Negotiation() {
  const [session, setSession] = useState<Session | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [term, setTerm] = useState(18)
  const [share, setShare] = useState(10)
  const [holiday, setHoliday] = useState(1)

  async function start() {
    setBusy(true)
    setError('')
    try {
      const result = await postJson<Session>('/negotiate/start', {
        applicant_id: APPLICANT_ID,
        persona: 'priya',
        requested_amount_inr: 400000,
        requested_term_months: 18,
        annual_interest_rate_pct: 12,
      })
      setSession(result)
      if (result.latest_borrower?.counteroffer) {
        setTerm(result.latest_borrower.counteroffer.term_months)
        setShare(result.latest_borrower.counteroffer.revenue_share_pct)
        setHoliday(result.latest_borrower.counteroffer.payment_holiday_months)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start negotiation')
    } finally {
      setBusy(false)
    }
  }

  async function respond(action: 'accept' | 'reject' | 'counter') {
    if (!session) return
    setBusy(true)
    setError('')
    try {
      const result = await postJson<Session>('/negotiate/respond', {
        session_id: session.session_id,
        action,
        counter_term_months: action === 'counter' ? term : undefined,
        counter_revenue_share_pct: action === 'counter' ? share : undefined,
        counter_payment_holiday_months: action === 'counter' ? holiday : undefined,
        note: action === 'counter' ? 'Borrower-adjusted counteroffer from dashboard' : undefined,
      })
      setSession(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update negotiation')
    } finally {
      setBusy(false)
    }
  }

  const proposal = session?.current_proposal
  const closed = ['agreement_reached', 'no_agreement', 'manual_review_required', 'rejected'].includes(session?.status || '')

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Agent negotiation"
        title="Lender meets borrower."
        detail="Two rule-based negotiation agents with simulated settlement. Same verified aggregates. No money moves."
        action={<Button onClick={start} disabled={busy}>{busy ? 'Working…' : session ? 'Restart' : 'Start negotiation'}</Button>}
      />

      <Notice tone="warning">
        {session?.simulation_banner
          || 'SIMULATED negotiation only. Two rule-based negotiation agents with simulated settlement. Terms are not lender-approved and do not move money.'}
      </Notice>
      {error && <Notice tone="error">{error}</Notice>}

      {session && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Status" value={session.status.replaceAll('_', ' ')} detail={`Round ${session.round} / ${session.max_rounds}`} icon={<Icon name="chat" />} />
            <MetricCard label="Avg income" value={money(session.evidence.average_monthly_income_inr, true)} detail={session.evidence.classification} icon={<Icon name="income" />} tone="gold" />
            <MetricCard label="Instalment" value={proposal ? money(proposal.monthly_installment_inr, true) : '—'} detail={proposal ? `${proposal.term_months} months` : 'No proposal'} icon={<Icon name="card" />} tone="green" />
            <MetricCard label="Revenue share" value={proposal ? `${proposal.revenue_share_pct}%` : '—'} detail={`Holiday · ${proposal?.payment_holiday_months ?? 0} mo`} icon={<Icon name="trend" />} tone="rose" />
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <GlassCard>
              <p className="text-[10px] font-semibold uppercase text-paypal">Lender Agent</p>
              <h2 className="mt-1 font-semibold">Current proposal</h2>
              {proposal ? (
                <dl className="mt-4 space-y-2 text-sm">
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Amount</dt><dd>{money(proposal.repayment_amount_inr)}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Term</dt><dd>{proposal.term_months} months</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Monthly</dt><dd>{money(proposal.monthly_installment_inr)}</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Revenue share</dt><dd>{proposal.revenue_share_pct}%</dd></div>
                  <div className="flex justify-between gap-3"><dt className="text-slate-500">Payment holiday</dt><dd>{proposal.payment_holiday_months} months</dd></div>
                </dl>
              ) : <p className="mt-4 text-sm text-slate-500">No active proposal.</p>}
              <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {(proposal?.reasons || []).map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            </GlassCard>

            <GlassCard>
              <p className="text-[10px] font-semibold uppercase text-amber-700">Borrower Agent</p>
              <h2 className="mt-1 font-semibold">Affordability review</h2>
              <p className="mt-2 text-sm">Decision: <span className="font-medium">{session.latest_borrower?.decision || 'pending'}</span></p>
              <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-600">
                {(session.latest_borrower?.concerns || []).map((c) => <li key={c}>{c}</li>)}
              </ul>
              {session.latest_borrower?.counteroffer && (
                <div className="mt-4 rounded-xl border border-[rgb(var(--line))] p-3 text-xs">
                  <p className="font-semibold">Suggested counter</p>
                  <p className="mt-1">{session.latest_borrower.counteroffer.term_months} mo · {session.latest_borrower.counteroffer.revenue_share_pct}% share · holiday {session.latest_borrower.counteroffer.payment_holiday_months}</p>
                </div>
              )}
            </GlassCard>
          </div>

          {!closed && (
            <GlassCard>
              <h2 className="font-semibold">Actions</h2>
              <p className="mt-1 text-xs text-slate-500">Accept, reject, or send a counteroffer. Settlement stays simulated.</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <label className="text-xs">Term (months)
                  <input className="mt-1 w-full rounded-xl border border-[rgb(var(--line))] bg-transparent px-3 py-2" type="number" min={1} max={60} value={term} onChange={(e) => setTerm(Number(e.target.value))} />
                </label>
                <label className="text-xs">Revenue share %
                  <input className="mt-1 w-full rounded-xl border border-[rgb(var(--line))] bg-transparent px-3 py-2" type="number" min={1} max={30} step={0.5} value={share} onChange={(e) => setShare(Number(e.target.value))} />
                </label>
                <label className="text-xs">Payment holiday
                  <input className="mt-1 w-full rounded-xl border border-[rgb(var(--line))] bg-transparent px-3 py-2" type="number" min={0} max={3} value={holiday} onChange={(e) => setHoliday(Number(e.target.value))} />
                </label>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => respond('accept')} disabled={busy}>Accept</Button>
                <Button variant="ghost" onClick={() => respond('counter')} disabled={busy}>Send counteroffer</Button>
                <Button variant="ghost" onClick={() => respond('reject')} disabled={busy}>Reject</Button>
              </div>
            </GlassCard>
          )}

          {session.settlement && (
            <Notice tone="success">
              {session.settlement.message} PayPal payout executed: {String(session.settlement.paypal_payout)}.
            </Notice>
          )}

          <GlassCard>
            <h2 className="font-semibold">Negotiation timeline</h2>
            <ol className="mt-4 space-y-3">
              {session.history.map((item, index) => (
                <li key={`${item.at}-${index}`} className="rounded-xl border border-[rgb(var(--line))] px-3 py-2 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                    <span>Round {item.round} · {item.event.replaceAll('_', ' ')}</span>
                    <span>{item.at}</span>
                  </div>
                  {'reasons' in item.payload && Array.isArray(item.payload.reasons) ? (
                    <p className="mt-1 text-xs text-slate-600">{(item.payload.reasons as string[]).slice(0, 2).join(' ')}</p>
                  ) : 'concerns' in item.payload && Array.isArray(item.payload.concerns) ? (
                    <p className="mt-1 text-xs text-slate-600">{(item.payload.concerns as string[]).slice(0, 2).join(' ')}</p>
                  ) : (
                    <p className="mt-1 text-xs text-slate-500">Simulated agent event</p>
                  )}
                </li>
              ))}
            </ol>
          </GlassCard>
        </>
      )}

      {!session && (
        <GlassCard>
          <h2 className="font-semibold">Ready when you are</h2>
          <p className="mt-2 text-sm text-slate-500">
            Starts from Priya&apos;s fixture income aggregates and a ₹4,00,000 / 18-month request. Both agents cite the same evidence.
          </p>
        </GlassCard>
      )}
    </div>
  )
}
