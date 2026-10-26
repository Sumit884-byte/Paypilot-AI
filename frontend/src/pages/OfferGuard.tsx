import { useState, type FormEvent, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Icon, inputClass, Notice, PageHeading, Field, Toast } from '../components/ui/Workspace'
import { postJson } from '../lib/api'

type OfferResult = {
  advertised_apr_pct: number
  estimated_real_apr_pct: number
  processing_fee_pct: number
  red_flag: boolean
  kfs_checklist: Array<{ item: string; ok: boolean }>
  rbi_directory_match: string
}

export function OfferGuard() {
  const [result, setResult] = useState<OfferResult | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [filePreview, setFilePreview] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) {
      setFile(f)
      if (f.type.startsWith('image/')) {
        const url = URL.createObjectURL(f)
        setFilePreview(url)
      } else {
        setFilePreview(null)
      }
    }
  }

  function clearFile() {
    setFile(null)
    setFilePreview(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const d = new FormData(e.currentTarget)
    const apr = Number(d.get('apr'))
    const fee = Number(d.get('fee'))
    const principal = Number(d.get('principal'))
    const months = Number(d.get('months'))

    // Client-side limit validation with clear popup messages
    if (!Number.isFinite(apr) || apr < 0 || apr > 100) {
      setToast('Advertised APR must be between 0% and 100%.')
      return
    }
    if (!Number.isFinite(fee) || fee < 0 || fee > 50) {
      setToast('Processing fee must be between 0% and 50%.')
      return
    }
    if (!Number.isFinite(principal) || principal <= 0 || principal > 1_000_000_000) {
      setToast('Principal must be between 1 INR and 1,000,000,000 INR.')
      return
    }
    if (!Number.isFinite(months) || months < 1 || months > 360) {
      setToast('Term must be between 1 and 360 months.')
      return
    }

    setAnalyzing(true)
    setError('')
    setToast(null)
    try {
      const response = await postJson<OfferResult>('/offer-guard', {
        advertised_apr_pct: apr,
        processing_fee_pct: fee,
        principal_inr: principal,
        term_months: months,
        lender_name: String(d.get('lender')),
      })
      setResult(response)
      sessionStorage.setItem('paypilot.offer', JSON.stringify(response))
    } catch (x) {
      setError(x instanceof Error ? x.message : 'Unable to check offer')
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Offer guard"
        title="Know the cost behind the offer."
        detail="Compare advertised APR with a simple fee-adjusted demo estimate."
      />
      <Notice>
        Sandbox demo only. Upload attaches locally; enter the offer terms below. RBI directory result is an
        illustrative heuristic, not verification.
      </Notice>

      {toast && (
        <Toast message={toast} onDismiss={() => setToast(null)} />
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <GlassCard>
          <form onSubmit={submit} onChange={() => setToast(null)} className="space-y-4">
            <h2 className="font-semibold">Offer details</h2>
            <div className="relative">
              <label className="flex cursor-pointer items-center gap-3 rounded-2xl border border-dashed border-paypal/40 p-4 text-sm transition hover:border-paypal hover:bg-paypal/5">
                <Icon name="upload" />
                <span>{file?.name || 'Attach screenshot or PDF (local only)'}</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  className="sr-only"
                  onChange={handleFileChange}
                />
              </label>
              {filePreview && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: 8 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: -8 }}
                  className="absolute bottom-full left-0 right-0 mb-2"
                >
                  <div className="relative max-w-xs mx-auto rounded-xl overflow-hidden border border-paypal/20 bg-white dark:bg-navy-900 shadow-glass">
                    <img src={filePreview} alt="Offer preview" className="w-full h-40 object-cover" />
                    <button
                      type="button"
                      onClick={clearFile}
                      className="absolute top-2 right-2 rounded-full bg-navy-950/80 p-1 text-white hover:bg-navy-950"
                      aria-label="Remove file"
                    >
                      <Icon name="menu" size={14} />
                    </button>
                  </div>
                </motion.div>
              )}
            </div>
            <Field label="Lender">
              <input name="lender" defaultValue="Example NBFC" className={inputClass} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Advertised APR (%)">
                <input required name="apr" type="number" step=".1" defaultValue="18" className={inputClass} />
              </Field>
              <Field label="Processing fee (%)">
                <input required name="fee" type="number" step=".1" defaultValue="4" className={inputClass} />
              </Field>
              <Field label="Principal (INR)">
                <input required name="principal" type="number" defaultValue="50000" className={inputClass} />
              </Field>
              <Field label="Term (months)">
                <input required name="months" type="number" defaultValue="12" className={inputClass} />
              </Field>
            </div>
            <Button type="submit" disabled={analyzing} className="w-full">
              {analyzing ? 'Analyzing offer…' : 'Analyze offer'}
            </Button>
          </form>
        </GlassCard>

        <GlassCard>
          <h2 className="font-semibold">Analysis result</h2>
          {error && <Notice tone="error">{error}</Notice>}

          <AnimatePresence mode="wait">
            {!result && !analyzing && !error && (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="py-12 text-center text-sm text-slate-500"
              >
                Enter offer details to see the breakdown
              </motion.div>
            )}

            {analyzing && (
              <motion.div
                key="analyzing"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="py-12 text-center"
              >
                <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-paypal border-t-transparent" />
                <p className="text-sm text-slate-500">Analyzing offer terms…</p>
              </motion.div>
            )}

            {result && (
              <motion.div
                key="result"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                className="space-y-4"
              >
                {/* Red Flag Highlight */}
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.1 }}
                  className={`rounded-2xl p-4 ${
                    result.red_flag
                      ? 'bg-rose-500/10 border-2 border-rose-500/30'
                      : 'bg-emerald-500/10 border-2 border-emerald-500/30'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon
                      name={result.red_flag ? 'shield' : 'check'}
                      className={result.red_flag ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}
                    />
                    <div>
                      <p className="font-semibold">
                        {result.red_flag ? 'Red flag detected' : 'Offer looks reasonable'}
                      </p>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        {result.red_flag
                          ? `Estimated real APR is ${(result.estimated_real_apr_pct - result.advertised_apr_pct).toFixed(1)} percentage points higher than advertised`
                          : 'Real APR is within acceptable range of advertised rate'}
                      </p>
                    </div>
                  </div>
                </motion.div>

                {/* APR Comparison */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-slate-100/50 p-4 dark:bg-white/5">
                    <p className="text-xs text-slate-500">Advertised APR</p>
                    <p className="mt-2 text-lg font-semibold">{result.advertised_apr_pct}%</p>
                  </div>
                  <div
                    className={`rounded-2xl p-4 ${
                      result.red_flag ? 'bg-rose-500/10' : 'bg-emerald-500/10'
                    }`}
                  >
                    <p className="text-xs text-slate-500">Real APR</p>
                    <p
                      className={`mt-2 text-lg font-semibold ${
                        result.red_flag ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
                      }`}
                    >
                      {result.estimated_real_apr_pct}%
                    </p>
                  </div>
                </div>

                {/* KFS Checklist */}
                <div>
                  <h3 className="mb-3 text-sm font-semibold">Key Fact Statement (KFS) checklist</h3>
                  <div className="space-y-2">
                    {result.kfs_checklist.map((item, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.2 + i * 0.08 }}
                        className={`flex items-center gap-3 rounded-xl p-3 ${item.ok ? 'bg-emerald-500/10' : 'bg-rose-500/10'}`}
                      >
                        <span
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-full ${item.ok ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'}`}
                        >
                          {item.ok ? 'OK' : 'Missing'}
                        </span>
                        <span className="text-sm">{item.item}</span>
                      </motion.div>
                    ))}
                  </div>
                </div>

                {/* RBI Directory Match */}
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.5 }}
                  className={`rounded-2xl p-4 ${
                    result.rbi_directory_match === 'match'
                      ? 'bg-emerald-500/10 border border-emerald-500/20'
                      : 'bg-amber-500/10 border border-amber-500/20'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <Icon
                      name={result.rbi_directory_match === 'match' ? 'check' : 'shield'}
                      className={`mt-0.5 ${
                        result.rbi_directory_match === 'match'
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-amber-600 dark:text-amber-400'
                      }`}
                    />
                    <div className="flex-1">
                      <p className="font-semibold">
                        {result.rbi_directory_match === 'match' ? 'Name heuristic matched bank/NBFC terms' : 'RBI directory match unverified'}
                      </p>
                      {result.rbi_directory_match === 'match' && (
                        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                          Lender-name match only; not an RBI verification.
                        </p>
                      )}
                      {result.rbi_directory_match !== 'match' && (
                        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                          This lender may not be registered with the Reserve Bank of India. Exercise caution.
                        </p>
                      )}
                    </div>
                  </div>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </GlassCard>
      </div>
    </div>
  )
}
