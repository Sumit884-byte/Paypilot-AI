import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { GlassCard } from '../components/ui/GlassCard'
import { Logo } from '../components/brand/Logo'
import { Notice } from '../components/ui/Workspace'
import { apiRequest, apiUrl, money } from '../lib/api'

type PublicPassport = {
  passport_reference: string
  verification_status: string
  integrity_status: string
  issued_at_utc: string
  expires_at_utc: string
  revoked_at_utc?: string | null
  borrower_display_name: string
  limited_financial_summary: {
    total_income_12m_inr: number
    average_monthly_income_inr: number | null
    income_consistency: string
    income_period: { window_start?: string; window_end?: string }
    income_classification: string
    verification_method: string
    evidence_source: string
  }
  pdf_share_enabled: boolean
  disclaimer: string
  decision_support_statement: string
}

export function VerifyIncomePassport() {
  const { token } = useParams<{ token: string }>()
  const [data, setData] = useState<PublicPassport | null>(null)
  const [fetchError, setError] = useState('')
  const [loading, setLoading] = useState(Boolean(token))
  const error = token ? fetchError : 'Missing verification token.'

  useEffect(() => {
    if (!token) return
    apiRequest<PublicPassport>(`/api/verify/income-passport/${encodeURIComponent(token)}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Passport not found'))
      .finally(() => setLoading(false))
  }, [token])

  const tone =
    data?.integrity_status === 'valid' ? 'success'
      : data?.integrity_status === 'revoked'
        || data?.integrity_status === 'expired'
        || data?.integrity_status === 'tampered' ? 'warning'
        : 'info'

  return (
    <div className="min-h-screen bg-[rgb(var(--bg))] px-4 py-10">
      <div className="mx-auto max-w-2xl space-y-5">
        <div className="flex items-center justify-between gap-3">
          <Logo />
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Public verification</span>
        </div>

        <GlassCard interactive={false}>
          <h1 className="font-display text-3xl">Income Passport</h1>
          <p className="mt-2 text-sm text-slate-500">No account required. Limited summary only.</p>

          {loading && <p className="mt-6 text-sm text-slate-500">Checking integrity…</p>}
          {error && <div className="mt-6"><Notice tone="error">{error}</Notice></div>}

          {data && (
            <div className="mt-6 space-y-5">
              <Notice tone={tone}>
                Integrity: <strong>{data.integrity_status}</strong> · Verification status: {data.verification_status}
              </Notice>

              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-xs text-slate-500">Reference</dt><dd className="font-medium">{data.passport_reference}</dd></div>
                <div><dt className="text-xs text-slate-500">Borrower</dt><dd className="font-medium">{data.borrower_display_name}</dd></div>
                <div><dt className="text-xs text-slate-500">Issued</dt><dd>{data.issued_at_utc}</dd></div>
                <div><dt className="text-xs text-slate-500">Expires</dt><dd>{data.expires_at_utc}</dd></div>
                <div><dt className="text-xs text-slate-500">Income (12m)</dt><dd>{money(data.limited_financial_summary.total_income_12m_inr)}</dd></div>
                <div><dt className="text-xs text-slate-500">Avg monthly</dt><dd>{data.limited_financial_summary.average_monthly_income_inr != null ? money(data.limited_financial_summary.average_monthly_income_inr) : 'Missing'}</dd></div>
                <div><dt className="text-xs text-slate-500">Consistency</dt><dd>{data.limited_financial_summary.income_consistency}</dd></div>
                <div><dt className="text-xs text-slate-500">Classification</dt><dd>{data.limited_financial_summary.income_classification}</dd></div>
                <div><dt className="text-xs text-slate-500">Period</dt><dd>{data.limited_financial_summary.income_period?.window_start} → {data.limited_financial_summary.income_period?.window_end}</dd></div>
                <div><dt className="text-xs text-slate-500">Method</dt><dd>{data.limited_financial_summary.verification_method}</dd></div>
              </dl>

              <Notice>{data.disclaimer}</Notice>
              <Notice tone="warning">{data.decision_support_statement}</Notice>

              {data.pdf_share_enabled && data.integrity_status === 'valid' && token && (
                <a
                  className="inline-flex text-sm font-medium text-paypal underline"
                  href={apiUrl(`/api/verify/income-passport/${encodeURIComponent(token)}/pdf`)}
                  target="_blank"
                  rel="noreferrer"
                >
                  View shared PDF
                </a>
              )}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  )
}
