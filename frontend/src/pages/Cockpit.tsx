import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Link } from 'react-router-dom'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Notice, PageHeading, Icon, inputClass } from '../components/ui/Workspace'
import { apiRequest, type Persona } from '../lib/api'

function usePersona() {
  const [p, setP] = useState<Persona | null>(null)
  useEffect(() => { apiRequest<Persona>('/demo/persona/priya').then(setP).catch(() => {}) }, [])
  return p
}

const widgetColors: Record<string, string> = {
  'Advertised vs real APR': 'from-rose-500/15 to-amber-500/15 border-rose-500/30',
  'Score drivers': 'from-paypal/15 to-amber-glow/15 border-paypal/30',
  'Repayment progress': 'from-emerald-500/15 to-teal-500/15 border-emerald-500/30',
  'Income by client': 'from-blue-500/15 to-indigo-500/15 border-blue-500/30',
  'Monthly cashflow': 'from-violet-500/15 to-purple-500/15 border-violet-500/30',
  'Risk analysis': 'from-rose-500/15 to-orange-500/15 border-rose-500/30',
}

export function Cockpit() {
  const [widgets, setWidgets] = useState(['Advertised vs real APR', 'Score drivers', 'Repayment progress'])
  const [q, setQ] = useState('')
  const p = usePersona()
  const [offer] = useState<any>(() => { try { return JSON.parse(sessionStorage.getItem('paypilot.offer') || 'null') } catch { return null } })
  const [score] = useState<any>(() => { try { return JSON.parse(sessionStorage.getItem('paypilot.score') || 'null') } catch { return null } })
  const [repayment, setRepayment] = useState<any[]>([])
  useEffect(() => { apiRequest<any>('/repayment/status?applicant_id=PSC-PRIYA-001').then((r) => setRepayment(r.entries ?? [])).catch(() => {}) }, [])

  function addWidget() {
    if (q.trim()) {
      setWidgets((v) => [...v, q.trim()])
      setQ('')
    }
  }

  function removeWidget(index: number) {
    setWidgets((v) => v.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="AG Studio"
        title="Your financial cockpit."
        detail="Bring the signals you care about into one workspace."
      />
      <Notice>
        Demo widgets use fixture values and heuristic score drivers; no live lending decision is made.
      </Notice>

      <GlassCard>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); addWidget() }}>
          <input
            aria-label="Ask for a cockpit widget"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask: show my income by client"
            className={inputClass}
          />
          <Button type="submit">Add widget</Button>
        </form>
      </GlassCard>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <AnimatePresence mode="popLayout">
          {widgets.map((w, i) => (
            <motion.div
              layout
              key={w + i}
              initial={{ opacity: 0, scale: 0.94, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: -12 }}
              transition={{ type: 'spring', stiffness: 180, damping: 20 }}
            >
              <GlassCard
                className={`min-h-48 bg-gradient-to-br ${widgetColors[w] || 'bg-slate-100/50 dark:bg-white/5'} border`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-paypal">
                      Widget {String(i + 1).padStart(2, '0')}
                    </p>
                    <h2 className="mt-3 font-semibold">{w}</h2>
                  </div>
                  <button
                    onClick={() => removeWidget(i)}
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200/50 hover:text-slate-600 dark:hover:bg-white/10 dark:hover:text-slate-200"
                    aria-label="Remove widget"
                  >
                    <Icon name="menu" size={14} />
                  </button>
                </div>

                {/* Widget-specific content */}
                <div className="mt-4 space-y-3">
                  {w.toLowerCase().includes('income by') && (
                    <>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Icon name="users" size={16} className="text-paypal" />
                          <span className="text-sm text-slate-600 dark:text-slate-300">
                            {p ? `${new Set(p.recent_transactions.map((t) => t.category)).size} categories` : 'Loading…'}
                          </span>
                        </div>
                        <span className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-400/10 px-2 py-1 rounded-full">
                          Demo data
                        </span>
                      </div>
                      <div className="h-24 rounded-xl bg-gradient-to-br from-paypal/5 to-paypal/10 border border-paypal/10 flex items-center justify-center relative overflow-hidden">
                        <svg viewBox="0 0 200 80" className="w-full h-full" aria-hidden>
                          <defs>
                            <linearGradient id="clientGrad1" x1="0" y1="1" x2="0" y2="0">
                              <stop offset="0%" stopColor="#0070BA" stopOpacity="0.6" />
                              <stop offset="100%" stopColor="#0070BA" stopOpacity="0" />
                            </linearGradient>
                            <linearGradient id="clientGrad2" x1="0" y1="1" x2="0" y2="0">
                              <stop offset="0%" stopColor="#F5B942" stopOpacity="0.6" />
                              <stop offset="100%" stopColor="#F5B942" stopOpacity="0" />
                            </linearGradient>
                            <linearGradient id="clientGrad3" x1="0" y1="1" x2="0" y2="0">
                              <stop offset="0%" stopColor="#10B981" stopOpacity="0.6" />
                              <stop offset="100%" stopColor="#10B981" stopOpacity="0" />
                            </linearGradient>
                            <linearGradient id="clientGrad4" x1="0" y1="1" x2="0" y2="0">
                              <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.6" />
                              <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0" />
                            </linearGradient>
                          </defs>
                          <rect x="20" y="40" width="32" height="35" rx="2" fill="url(#clientGrad1)" />
                          <rect x="64" y="20" width="32" height="55" rx="2" fill="url(#clientGrad2)" />
                          <rect x="108" y="50" width="32" height="25" rx="2" fill="url(#clientGrad3)" />
                          <rect x="152" y="30" width="32" height="45" rx="2" fill="url(#clientGrad4)" />
                          <text x="36" y="78" textAnchor="middle" fontSize="8" fill="currentColor" opacity="0.5" fontFamily="system-ui">Client A</text>
                          <text x="80" y="78" textAnchor="middle" fontSize="8" fill="currentColor" opacity="0.5" fontFamily="system-ui">Client B</text>
                          <text x="124" y="78" textAnchor="middle" fontSize="8" fill="currentColor" opacity="0.5" fontFamily="system-ui">Client C</text>
                          <text x="168" y="78" textAnchor="middle" fontSize="8" fill="currentColor" opacity="0.5" fontFamily="system-ui">Client D</text>
                        </svg>
                        <motion.div
                          className="absolute inset-0 flex items-center justify-center"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 0.6 }}
                          transition={{ delay: 0.5, duration: 1.5, repeat: Infinity, repeatType: "reverse" }}
                        >
                          <span className="text-[10px] text-slate-400 uppercase tracking-wider">Client identities not in fixture data</span>
                        </motion.div>
                      </div>
                    </>
                  )}

                  {w.toLowerCase().includes('apr') && (
                    <>
                      <div className="flex items-center justify-between rounded-xl bg-rose-500/10 p-3">
                        <span className="text-xs text-slate-600 dark:text-slate-300">Advertised</span>
                        <span className="font-semibold text-rose-600 dark:text-rose-400">{offer ? `${offer.advertised_apr_pct}%` : '—'}</span>
                      </div>
                      <div className="flex items-center justify-between rounded-xl bg-emerald-500/10 p-3">
                        <span className="text-xs text-slate-600 dark:text-slate-300">Real</span>
                        <span className="font-semibold text-emerald-600 dark:text-emerald-400">{offer ? `${offer.estimated_real_apr_pct}%` : '—'}</span>
                      </div>
                    </>
                  )}

                  {w.toLowerCase().includes('score') && (
                    <>
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-paypal/20 text-paypal" />
                        <div className="flex-1">
                          <div className="h-2 rounded-full bg-slate-200 dark:bg-white/10">
                            <div className="h-full w-3/4 rounded-full bg-gradient-to-r from-paypal to-amber-glow" />
                          </div>
                        </div>
                      </div>
                      <p className="text-xs text-slate-500">{score ? `PayScore ${score.score} · ${score.risk_band} risk · heuristic drivers, not SHAP` : 'Run PayScore to view current signals'}</p>
                    </>
                  )}

                  {w.toLowerCase().includes('repayment') && (
                    <>
                      <div className="flex items-center gap-2">
                        <Icon name="clock" size={16} className="text-emerald-500" />
                        <span className="text-sm text-slate-600 dark:text-slate-300">{repayment.filter((r) => r.status === 'COMPLETED').length} completed ledger entries</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-200 dark:bg-white/10">
                        <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(100, repayment.filter((r) => r.status === 'COMPLETED').length * 100 / Math.max(1, repayment.length))}%` }} />
                      </div>
                    </>
                  )}

                  {w.toLowerCase().includes('cashflow') && (
                    <div className="h-20 rounded-xl bg-paypal/5 flex items-center justify-center">
                      <Icon name="income" size={32} className="text-paypal/30" />
                    </div>
                  )}

                  {w.toLowerCase().includes('risk') && (
                    <div className="flex items-center gap-2">
                      <Icon name="shield" size={16} className="text-amber-500" />
                      <span className="text-sm text-slate-600 dark:text-slate-300">Moderate risk detected</span>
                    </div>
                  )}
                </div>

                <Link
                  to={
                    w.toLowerCase().includes('apr')
                      ? '/app/offer-guard'
                      : w.toLowerCase().includes('score')
                        ? '/app/score'
                        : w.toLowerCase().includes('repayment')
                          ? '/app/repay'
                          : '/app/income'
                  }
                  className="mt-5 inline-flex items-center gap-2 text-xs font-semibold text-paypal hover:underline"
                >
                  Open source <Icon name="arrow" size={12} />
                </Link>
              </GlassCard>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
