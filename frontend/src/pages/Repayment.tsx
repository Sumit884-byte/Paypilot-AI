import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Icon, inputClass, Notice, PageHeading, Field } from '../components/ui/Workspace'
import { ConfettiBurst } from '../components/ui/Confetti'
import { SuccessAnimation } from '../components/ui/SuccessAnimation'
import { apiRequest, postJson } from '../lib/api'
import { useActivePersona } from '../lib/personas'

const demoNotice = 'Sandbox demo only · No real money movement.'

type ScheduleItem = {
  installment: number
  due_date: string
  amount_inr: number
  paypal_amount_usd: number
}

type RepaymentEntry = {
  mode: string
  status?: string
  subscription_id?: string
  order_id?: string
  event_id?: string
  entry?: any
}

export function Repayment() {
  const persona = useActivePersona()
  const applicant = persona.applicantId
  const [mode, setMode] = useState<'fixed' | 'revenue' | 'one-off'>('fixed')
  const [schedule, setSchedule] = useState<ScheduleItem[]>([])
  const [_entries, setEntries] = useState<RepaymentEntry[]>([])
  const [confetti, setConfetti] = useState(false)
  const [error, setError] = useState('')
  const [liveScore, setLiveScore] = useState<any>(null)
  const [scoreUpdated, setScoreUpdated] = useState(false)
  const previousLiveScore = useRef<number | null>(null)
  const [readyCheckout, setReadyCheckout] = useState<string | null>(null)
  const paypalSession = useRef<any>(null)
  const [payoutBatchId, setPayoutBatchId] = useState(() => sessionStorage.getItem('paypilot.payout_batch_id') || '')
  const [payoutStatus, setPayoutStatus] = useState('')
  const completedBatch = useRef('')

  const [amount, setAmount] = useState('5000')
  const [count, setCount] = useState('12')
  const [paypalOrderId, setPaypalOrderId] = useState('')
  const paypalReady = mode === 'one-off' && !!paypalOrderId && readyCheckout === paypalOrderId

  useEffect(() => {
    apiRequest<any>('/repayment/status?applicant_id=' + applicant)
      .then((r) => setEntries(r.entries ?? []))
      .catch(() => {})

    const timer = setInterval(
      () =>
        apiRequest<any>('/repayment/status?applicant_id=' + applicant)
          .then((r) => setEntries(r.entries ?? []))
          .catch(() => {}),
      15000
    )
    return () => clearInterval(timer)
  }, [applicant])

  useEffect(() => {
    if (!payoutBatchId) return
    let active = true
    const pollPayout = async () => {
      try {
        const result = await apiRequest<any>(`/disburse/${encodeURIComponent(payoutBatchId)}`)
        if (!active) return
        const current = result.batch_status || 'PENDING'
        setPayoutStatus(current)
        if (['SUCCESS', 'COMPLETED'].includes(current) && completedBatch.current !== payoutBatchId) {
          completedBatch.current = payoutBatchId
          setConfetti(true)
          window.setTimeout(() => setConfetti(false), 4500)
        }
      } catch {
        if (active) setPayoutStatus('Status unavailable; retrying')
      }
    }
    void pollPayout()
    const timer = window.setInterval(pollPayout, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [payoutBatchId])

  // Poll for live score updates
  useEffect(() => {
    const timer = setInterval(
      () =>
        apiRequest<any>(`/score/live?applicant_id=${applicant}`)
          .then((r) => {
            if (r.score) {
              if (previousLiveScore.current !== null && previousLiveScore.current !== r.score) {
                setScoreUpdated(true)
                window.setTimeout(() => setScoreUpdated(false), 4500)
              }
              previousLiveScore.current = r.score
              setLiveScore(r)
            }
          })
          .catch(() => {}),
      5000
    )
    return () => clearInterval(timer)
  }, [applicant])

  async function createFixed() {
    try {
      const r = await postJson<any>('/repayment/subscription', {
        applicant_id: applicant,
        subscriber_email: persona.email,
        emi_amount_inr: Number(amount),
        number_of_emis: Number(count),
        note: 'PayScore demo fixed EMI',
      })
      setSchedule(r.repayment_schedule ?? [])
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Subscription needs configured sandbox credentials')
    }
  }

  async function createOrder() {
    try {
      const r = await postJson<any>('/repayment/order', {
        applicant_id: applicant,
        emi_amount_inr: Number(amount),
        note: 'PayScore demo one-off EMI',
      })
      setSchedule(r.repayment_schedule ?? [])
      setPaypalOrderId(r.orderId || r.order_id || '')
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Order needs configured sandbox credentials')
    }
  }

  async function share() {
    try {
      const r = await postJson<any>('/repayment/revenue-share', {
        applicant_id: applicant,
        paypal_account_id: persona.paypalDemoId,
        percentage: 5,
      })
      setSchedule(r.repayment_schedule ?? [])
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not set revenue share')
    }
  }

  // PayPal JS SDK v6 sandbox session, created only after the API returns an order id.
  useEffect(() => {
    if (mode !== 'one-off' || !paypalOrderId) return
    let active = true
    const initialize = async () => {
      try {
        const config = await apiRequest<{ client_id: string; mode: string }>('/paypal/public-config')
        if (config.mode !== 'sandbox' || !config.client_id) throw new Error('Sandbox client id is unavailable.')
        const win = window as any
        const launch = async () => {
          try {
            const instance = await win.paypal.createInstance({ clientId: config.client_id, components: ['paypal-payments'] })
            paypalSession.current = instance.createPayPalOneTimePaymentSession({
              onApprove: async (data: any) => {
                const result = await postJson<any>(`/repayment/order/${data.orderId || paypalOrderId}/capture`, {})
                setSchedule(result.repayment_schedule ?? [])
                setConfetti(true)
                window.setTimeout(() => setConfetti(false), 4500)
              },
              onCancel: () => setError('Checkout cancelled. No repayment was captured.'),
              onError: (err: any) => setError(err?.message || 'PayPal checkout failed.'),
            })
            if (active) setReadyCheckout(paypalOrderId)
          } catch (err) { if (active) setError(err instanceof Error ? err.message : 'PayPal SDK could not initialize.') }
        }
        if (win.paypal?.createInstance) { await launch(); return }
        let script = document.querySelector<HTMLScriptElement>('script[data-paypal-sdk-v6]')
        if (!script) {
          script = document.createElement('script')
          script.src = 'https://www.sandbox.paypal.com/web-sdk/v6/core'
          script.dataset.paypalSdkV6 = 'true'
          document.head.appendChild(script)
        }
        script.addEventListener('load', launch, { once: true })
        script.addEventListener('error', () => { if (active) setError('Could not load PayPal sandbox checkout.') }, { once: true })
      } catch (err) { if (active) setError(err instanceof Error ? err.message : 'PayPal sandbox configuration unavailable.') }
    }
    void initialize()
    return () => { active = false; paypalSession.current = null }
  }, [mode, paypalOrderId])

  async function startPaypalCheckout() {
    if (!paypalSession.current || !paypalOrderId) return
    setError('')
    try {
      await paypalSession.current.start({ presentationMode: 'auto' }, Promise.resolve({ orderId: paypalOrderId }))
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not open PayPal checkout.') }
  }

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Repayment"
        title="A clear path to paid back."
        detail="Fixed EMI, revenue share, or one-off payments via PayPal."
      />
      <Notice>{demoNotice}</Notice>

      {/* Mode Toggle */}
      <GlassCard>
        <div className="flex gap-2">
          {[
            { id: 'fixed', label: 'Fixed EMI' },
            { id: 'revenue', label: 'Revenue share' },
            { id: 'one-off', label: 'One-off' },
          ].map((m) => (
            <button
              key={m.id}
              onClick={() => setMode(m.id as any)}
              className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
                mode === m.id
                  ? 'bg-paypal text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-300 dark:hover:bg-white/15'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </GlassCard>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Setup Form */}
        <GlassCard>
          <h2 className="font-semibold">Configure repayment</h2>
          <div className="mt-4 space-y-4">
            {mode === 'fixed' && (
              <>
                <Field label="EMI amount (INR)">
                  <input
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    type="number"
                    className={inputClass}
                  />
                </Field>
                <Field label="Number of EMIs">
                  <input
                    value={count}
                    onChange={(e) => setCount(e.target.value)}
                    type="number"
                    className={inputClass}
                  />
                </Field>
                <Button onClick={createFixed} className="w-full">
                  Create subscription
                </Button>
              </>
            )}

            {mode === 'revenue' && (
              <>
                <Field label="Revenue share percentage">
                  <input defaultValue="5" type="number" step="0.1" className={inputClass} />
                </Field>
                <Field label="PayPal account ID">
                  <input defaultValue={persona.paypalDemoId} className={inputClass} />
                </Field>
                <Button onClick={share} className="w-full">
                  Configure revenue share
                </Button>
              </>
            )}

            {mode === 'one-off' && (
              <>
                <Field label="One-off EMI amount (INR)">
                  <input
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    type="number"
                    className={inputClass}
                  />
                </Field>
                <Button onClick={createOrder} className="w-full">
                  Create order
                </Button>
                {paypalOrderId && (
                  <div className="mt-4">
                    <p className="mb-2 text-xs text-slate-500">Approve this one-off EMI in PayPal sandbox checkout.</p>
                    <Button variant="gold" onClick={startPaypalCheckout} disabled={!paypalReady} className="w-full">
                      {paypalReady ? 'Pay with PayPal' : 'Loading PayPal checkout…'}
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        </GlassCard>

        {/* Schedule */}
        <GlassCard>
          <h2 className="font-semibold">Repayment schedule</h2>
          {schedule.length > 0 ? (
            <div className="mt-4 space-y-2 max-h-80 overflow-y-auto">
              {schedule.map((item, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-center justify-between rounded-xl bg-slate-100/50 p-3 dark:bg-white/5"
                >
                  <div>
                    <p className="text-xs text-slate-500">Installment {item.installment}</p>
                    <p className="text-sm font-semibold">{item.due_date}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold">₹{item.amount_inr.toLocaleString()}</p>
                    <p className="text-xs text-slate-500">${item.paypal_amount_usd.toFixed(2)}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-center text-sm text-slate-500">No schedule configured yet</p>
          )}
        </GlassCard>
      </div>

      {payoutBatchId && (
        <GlassCard className="border-paypal/20">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-paypal">Sandbox payout</p>
              <label className="mt-2 block text-[11px] text-slate-500">Payout batch id
                <input value={payoutBatchId} onChange={(event) => { setPayoutBatchId(event.target.value); sessionStorage.setItem('paypilot.payout_batch_id', event.target.value) }} className={`${inputClass} mt-1 font-mono`} />
              </label>
            </div>
            <span className={`rounded-full px-3 py-1 text-xs font-bold ${['SUCCESS', 'COMPLETED'].includes(payoutStatus) ? 'bg-emerald-500/15 text-emerald-600' : 'bg-amber-400/15 text-amber-700'}`}>
              {payoutStatus || 'Checking status…'}
            </span>
          </div>
          {['SUCCESS', 'COMPLETED'].includes(payoutStatus) && <div className="mt-4 flex items-center gap-3"><SuccessAnimation /><p className="text-sm font-semibold">Sandbox payout landed.</p></div>}
          <p className="mt-2 text-[11px] text-slate-500">Status refreshes from the PayPal Payouts API every five seconds.</p>
        </GlassCard>
      )}

      {/* Live Score Update */}
      <AnimatePresence>
        {liveScore && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -12 }}
            className="rounded-2xl bg-gradient-to-r from-paypal/10 to-amber-glow/10 border border-paypal/30 p-4"
          >
            <div className="flex items-center gap-3">
              <motion.div
                animate={scoreUpdated ? { scale: [1, 1.8, 1], opacity: [0.4, 1, 0.4], boxShadow: ['0 0 0px #0070ba', '0 0 18px #0070ba', '0 0 0px #0070ba'] } : { scale: 1, opacity: 0.75 }}
                transition={{ duration: scoreUpdated ? 1.1 : 0.3, repeat: scoreUpdated ? 2 : 0, ease: 'easeInOut' }}
                className="h-3 w-3 rounded-full bg-paypal"
              />
              <div className="flex-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-paypal">{scoreUpdated ? 'Score updated live' : 'Live score connected'}</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-sm">
                    New PayScore: <span className="font-bold">{liveScore.score}</span>
                  </p>
                  <motion.span
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
                      liveScore.risk_band === 'low'
                        ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                        : liveScore.risk_band === 'moderate'
                          ? 'bg-amber-400/20 text-amber-700 dark:text-amber-300'
                          : 'bg-rose-500/20 text-rose-700 dark:text-rose-300'
                    }`}
                  >
                    {liveScore.risk_band}
                  </motion.span>
                </div>
              </div>
              <motion.div
                animate={scoreUpdated ? { rotate: 360, scale: [1, 1.2, 1] } : { rotate: 0, scale: 1 }}
                transition={{ duration: 0.8, repeat: scoreUpdated ? 1 : 0, ease: 'easeInOut' }}
                className="text-paypal"
              >
                <Icon name="trend" size={20} />
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Confetti Animation */}
      <ConfettiBurst active={confetti} />

      <AnimatePresence>
        {confetti && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 grid place-items-center bg-navy-950/80 backdrop-blur-sm"
          >
            <div className="text-center">
              <SuccessAnimation />
              <motion.h2
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.6 }}
                className="mt-6 text-2xl font-bold text-white"
              >
                Payment successful!
              </motion.h2>
              <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7 }}
                className="mt-2 text-slate-300"
              >
                Your EMI has been recorded
              </motion.p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && <Notice tone="error">{error}</Notice>}
    </div>
  )
}
