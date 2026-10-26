import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Notice, PageHeading, ProgressRing, Icon } from '../components/ui/Workspace'
import { apiRequest, postJson, type Persona } from '../lib/api'

type Factor = {
  feature?: string
  label?: string
  name?: string
  contribution?: number
  direction?: string
  description?: string
  message?: string
  impact?: string
}

type Score = {
  score: number
  risk_band: string
  probability_of_default: number
  approved_amount_limit_inr: number
  disbursement_eligible: boolean
  drivers: Factor[]
  to_move_up: string
  explanation?: {
    status?: string
    method?: string | null
    detail?: string
    interpretation?: string
    factors_lowering_risk?: Factor[]
    factors_raising_risk?: Factor[]
  }
  counterfactual_preview?: { status?: string; summary?: string } | null
}

const demoNotice = 'Synthetic demo data · PayPal sandbox only · no real lending or money movement.'

function usePersona() {
  const [p, setP] = useState<Persona | null>(null)
  useEffect(() => {
    apiRequest<Persona>('/demo/persona/priya').then(setP).catch(() => {})
  }, [])
  return p
}

export function Score() {
  const p = usePersona()
  const [score, setScore] = useState<Score | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem('paypilot.score') || 'null')
    } catch {
      return null
    }
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [options, setOptions] = useState<Array<{ changes: Array<{ description: string }>; estimated_score: number; estimated_score_difference: number }>>([])

  async function run() {
    if (!p) return
    setBusy(true)
    setError('')
    try {
      const v = await postJson<Score>('/score', p.model_input)
      setScore(v)
      sessionStorage.setItem('paypilot.score', JSON.stringify(v))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not score this profile')
    } finally {
      setBusy(false)
    }
  }

  async function loadOptions() {
    if (!p) return
    setError('')
    try {
      const result = await postJson<{ suggestions?: typeof options; summary?: string; status?: string }>('/counterfactuals', p.model_input)
      setOptions(result.suggestions ?? [])
      if (!result.suggestions?.length) setError(result.summary || 'No eligible model-scored change raised the score.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not evaluate changes')
    }
  }

  const lowering = score?.explanation?.factors_lowering_risk ?? []
  const raising = score?.explanation?.factors_raising_risk ?? []
  const shapReady = score?.explanation?.status === 'available'

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="PayScore"
        title="A score with a story."
        detail="Review the signals behind this sandbox estimate."
        action={<Button onClick={run} disabled={!p || busy}>{busy ? 'Scoring…' : 'Run PayScore'}</Button>}
      />
      <Notice>{demoNotice}</Notice>
      {error && <Notice tone="error">{error}</Notice>}

      <div className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
        <GlassCard className="grid place-items-center py-8">
          <div className="relative">
            <ProgressRing
              value={score ? Math.max(0, Math.min(1, (score.score - 300) / 550)) : 0}
              size={220}
              stroke={14}
              label={score?.score ?? '—'}
              sublabel="PayScore"
            />
            <motion.div
              aria-hidden="true"
              initial={{ rotate: -135 }}
              animate={{ rotate: score ? -135 + ((score.score - 300) / 550) * 270 : -135 }}
              transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1] }}
              className="pointer-events-none absolute left-1/2 top-1/2 z-10 h-[72px] w-[3px] -translate-x-1/2 -translate-y-full origin-bottom rounded-full bg-gradient-to-t from-paypal to-amber-400 shadow-[0_0_12px_rgba(0,112,186,.45)]"
            />
            <div className="mt-4 text-center">
              <AnimatePresence mode="wait">
                {score && (
                  <motion.span
                    key={score.risk_band}
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    className={`inline-block rounded-full px-3 py-1 text-xs font-semibold capitalize ${
                      score.risk_band === 'low'
                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                        : score.risk_band === 'moderate'
                          ? 'bg-amber-400/15 text-amber-700 dark:text-amber-300'
                          : score.risk_band === 'elevated'
                            ? 'bg-orange-500/15 text-orange-700 dark:text-orange-300'
                            : 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                    }`}
                  >
                    {score.risk_band}
                  </motion.span>
                )}
              </AnimatePresence>
              <p className="mt-3 text-xs text-slate-500">Range 300–850 · demo estimate</p>
            </div>
          </div>
        </GlassCard>

        <GlassCard>
          <h2 className="font-semibold">What shaped this result</h2>
          <p className="mt-1 text-xs text-slate-500">
            {shapReady
              ? 'TreeSHAP log-odds for this model score. Attributions, not causes.'
              : score?.explanation?.detail || 'Run PayScore to request a SHAP explanation.'}
          </p>
          <div className="mt-5 space-y-3">
            <AnimatePresence mode="popLayout">
              {(shapReady ? [...lowering, ...raising] : score?.drivers ?? []).map((d, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 18 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -18 }}
                  transition={{ delay: i * 0.12 }}
                  className="rounded-2xl border border-slate-200/70 p-4 dark:border-white/10"
                >
                  <div className="flex gap-3">
                    <span className="grid h-9 w-9 place-items-center rounded-xl bg-paypal/10 text-paypal">
                      <Icon name={i === 0 ? 'trend' : 'shield'} />
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-semibold">{d.label || d.name || d.feature}</p>
                      <p className="mt-1 text-xs text-slate-500">{d.description || d.impact}</p>
                      {typeof d.contribution === 'number' && (
                        <p className="mt-1 text-xs font-medium">
                          {d.direction === 'lowers_risk' ? 'Lowers estimated risk' : 'Raises estimated risk'}
                          {' · '}
                          {(d.contribution > 0 ? '+' : '') + d.contribution.toFixed(4)} log-odds
                        </p>
                      )}
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {score?.to_move_up && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="mt-5 rounded-2xl bg-amber-400/10 p-4"
            >
              <div className="flex items-start gap-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-amber-400/20 text-amber-600 dark:text-amber-300">
                  <Icon name="arrow" />
                </span>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">
                    To move up
                  </p>
                  <p className="mt-1 text-sm">{score.to_move_up}</p>
                  <Button variant="ghost" className="mt-3" onClick={() => { void loadOptions() }} disabled={!p}>See eligible changes</Button>
                  {options.length > 0 && (
                    <ul className="mt-3 space-y-2 text-sm">
                      {options.map((option, index) => (
                        <li key={index}>
                          Estimated score {option.estimated_score} ({(option.estimated_score_difference > 0 ? '+' : '') + option.estimated_score_difference}). {option.changes.map((change) => change.description).join(' ')}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </GlassCard>
      </div>

      {score && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
        >
          <GlassCard>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-semibold">Disbursement eligibility</h2>
                <p className="mt-1 text-xs text-slate-500">
                  {score.disbursement_eligible
                    ? 'Score meets the threshold for sandbox disbursement'
                    : 'Score below threshold for disbursement'}
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  score.disbursement_eligible
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                    : 'bg-rose-500/15 text-rose-700 dark:text-rose-300'
                }`}
              >
                {score.disbursement_eligible ? 'Eligible' : 'Not eligible'}
              </span>
            </div>
            {score.disbursement_eligible && (
              <div className="mt-4 flex items-center justify-between rounded-2xl bg-paypal/5 p-4">
                <span className="text-sm text-slate-600 dark:text-slate-300">Approved limit</span>
                <span className="font-display text-lg font-bold">
                  {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(
                    score.approved_amount_limit_inr
                  )}
                </span>
              </div>
            )}
          </GlassCard>
        </motion.div>
      )}
    </div>
  )
}
