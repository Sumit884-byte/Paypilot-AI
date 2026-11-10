import { useState, type FormEvent, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Icon, inputClass, Notice, PageHeading, Field, Toast } from '../components/ui/Workspace'
import { postForm, postJson } from '../lib/api'
import { PayLaterCompare, type OfferTerms } from '../components/offer-guard/PayLaterCompare'

type OfferField = { value?: number | string | null; status?: string; note?: string; verified?: boolean }

type OfferResult = {
  advertised_apr_pct: number | null
  estimated_real_apr_pct: number | null
  processing_fee_pct: number | null
  red_flag: boolean
  comparison_status?: string
  kfs_checklist: Array<{ item: string; ok: boolean; status?: string }>
  rbi_directory_match: string
  warnings?: string[]
  missing_or_unverified_fields?: string[]
  fields?: Record<string, OfferField>
  directory?: { warning?: string; source_url?: string; retrieved_at?: string | null; confirmed_violation?: boolean; load_status?: string }
  extraction?: { ocr_status?: string; llm_status?: string; llm_reason?: string; text_chars?: number }
  injection_detected?: boolean
  injection_reasons?: string[]
  calculation?: { method?: string; formula?: string; pricing_basis?: string | null; installment_inr?: number | null }
  disclaimer?: string
}

export function OfferGuard() {
  const [result, setResult] = useState<OfferResult | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [filePreview, setFilePreview] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [terms, setTerms] = useState<OfferTerms>({ advertised_apr_pct: 18, processing_fee_pct: 4, principal: 50000, term_months: 12, lender_name: 'Example NBFC' })
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

    if (file && file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setToast('Only a PDF is parsed. Remove the file to use the manual form.')
      return
    }

    setAnalyzing(true)
    setError('')
    setToast(null)
    setTerms({ advertised_apr_pct: apr, processing_fee_pct: fee, principal, term_months: months, lender_name: String(d.get('lender')) })
    try {
      const response = file
        ? await postForm<OfferResult>('/offer-guard/upload', (() => {
            const body = new FormData()
            body.append('file', file)
            return body
          })())
        : await postJson<OfferResult>('/offer-guard', {
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
        title="The real cost, in plain sight."
        detail="Upload a loan-offer PDF or enter the terms. The effective cost is a monthly IRR on the cash flows."
      />
      <Notice>
        Sandbox estimate. Upload a text PDF or enter the terms manually. The cost is a monthly IRR, not a legal finding.
        A directory result is unverified unless a retrieved RBI list is loaded, and a name miss is not a confirmed violation.
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
                <span>{file?.name || 'Upload a loan-offer PDF, or leave this empty and use the form'}</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  onChange={handleFileChange}
                />
              </label>
              {file && !filePreview && (
                <button
                  type="button"
                  onClick={clearFile}
                  className="mt-2 text-xs font-semibold text-paypal underline underline-offset-4"
                >
                  Remove file
                </button>
              )}
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
                {result.injection_detected && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.1 }}
                    className="rounded-2xl p-4 bg-rose-500/10 border-2 border-rose-500/30"
                  >
                    <div className="flex items-start gap-3">
                      <Icon name="shield" className="mt-0.5 text-rose-600 dark:text-rose-400" />
                      <div>
                        <p className="font-semibold text-rose-800 dark:text-rose-200">
                          Hidden instructions found in this PDF
                        </p>
                        <p className="mt-1 text-sm text-rose-700 dark:text-rose-300">
                          Extraction was blocked and no AI model read it.
                          {result.injection_reasons?.length ? (
                            <span> Reasons: {result.injection_reasons.join(", ")}.</span>
                          ) : null}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                )}
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
                        {result.comparison_status === 'not_compared'
                          ? 'Not enough terms to compare'
                          : result.red_flag
                            ? 'Advertised APR is below the calculated cost'
                            : 'Calculated cost is within 1 point of the advertised APR'}
                      </p>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        {result.calculation?.formula || 'Monthly IRR of net proceeds and instalments. Not a legal finding.'}
                      </p>
                    </div>
                  </div>
                </motion.div>

                {/* APR Comparison */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-slate-100/50 p-4 dark:bg-white/5">
                    <p className="text-xs text-slate-500">Advertised APR</p>
                    <p className="mt-2 text-lg font-semibold">{result.advertised_apr_pct ?? '—'}{result.advertised_apr_pct == null ? '' : '%'}</p>
                  </div>
                  <div
                    className={`rounded-2xl p-4 ${
                      result.red_flag ? 'bg-rose-500/10' : 'bg-emerald-500/10'
                    }`}
                  >
                    <p className="text-xs text-slate-500">Effective annualised cost</p>
                    <p
                      className={`mt-2 text-lg font-semibold ${
                        result.red_flag ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'
                      }`}
                    >
                      {result.estimated_real_apr_pct ?? '—'}{result.estimated_real_apr_pct == null ? '' : '%'}
                    </p>
                  </div>
                </div>

                {result.fields && (
                  <div>
                    <h3 className="mb-3 text-sm font-semibold">Extracted terms</h3>
                    <div className="space-y-2">
                      {Object.entries(result.fields).filter(([, field]) => field.value != null).map(([name, field]) => (
                        <div key={name} className="flex items-start justify-between gap-3 rounded-xl bg-slate-100/60 p-3 text-sm dark:bg-white/5">
                          <span>{name.replaceAll('_', ' ')}</span>
                          <span className="text-right">
                            {String(field.value)}
                            <span className="mt-1 block text-xs text-slate-500">{field.status}{field.verified ? '' : ' · not verified'}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {!!result.warnings?.length && (
                  <div className="space-y-2">
                    {result.warnings.map((warning) => <Notice key={warning}>{warning}</Notice>)}
                  </div>
                )}
                {!!result.missing_or_unverified_fields?.length && (
                  <p className="text-xs text-slate-500">Missing or unverified: {result.missing_or_unverified_fields.join(', ')}</p>
                )}

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
                        {result.rbi_directory_match === 'match'
                          ? 'Possible name match in the retrieved list'
                          : result.rbi_directory_match === 'no_match'
                            ? 'No close name in the retrieved list'
                            : 'RBI list could not be verified'}
                      </p>
                      <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                        {result.directory?.warning || 'This is not a confirmed regulatory violation.'}
                        {result.directory?.source_url ? ` Source: ${result.directory.source_url}.` : ''}
                        {result.directory?.retrieved_at ? ` Retrieved: ${result.directory.retrieved_at}.` : ' No retrieval date is stored.'}
                      </p>
                    </div>
                  </div>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </GlassCard>
      </div>

      <PayLaterCompare key={JSON.stringify(terms)} terms={terms} />
    </div>
  )
}
