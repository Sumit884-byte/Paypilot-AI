import { useCallback, useEffect, useState } from 'react'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Notice, PageHeading, MetricCard, Icon } from '../components/ui/Workspace'
import { apiRequest, apiUrl, money, postJson } from '../lib/api'

const APPLICANT_ID = 'PSC-PRIYA-001'

type PassportView = {
  passport_id: string
  passport_reference: string
  applicant_id: string
  verification_status: string
  integrity_status: string
  issued_at_utc: string
  expires_at_utc: string
  revoked_at_utc?: string | null
  verification_token?: string
  verification_path?: string
  include_pdf_share?: boolean
  borrower_display_name?: string
  snapshot?: {
    income_summary: Record<string, { value: unknown; classification: string }>
    verification: { method: string; evidence_source: string; status: string; disclaimer: string }
  }
  limited_financial_summary?: {
    total_income_12m_inr: number
    average_monthly_income_inr: number | null
    income_consistency: string
    income_classification: string
  }
  disclaimer?: string
}

export function IncomePassport() {
  const [passport, setPassport] = useState<PassportView | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [copied, setCopied] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const view = await apiRequest<PassportView>(`/income-passport?applicant_id=${encodeURIComponent(APPLICANT_ID)}`)
      setPassport(view)
      setError('')
    } catch (e) {
      const status = e && typeof e === 'object' && 'status' in e ? Number((e as { status: number }).status) : 0
      if (status === 404) {
        setPassport(null)
        return
      }
      setError(e instanceof Error ? e.message : 'Could not load passport')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function generate() {
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      const view = await postJson<PassportView>('/income-passport', {
        applicant_id: APPLICANT_ID,
        persona: 'priya',
        ttl_days: 30,
        include_pdf_share: false,
      })
      setPassport(view)
      setSuccess('Income Passport generated. Copy the verification link to share a limited public summary.')
    } catch (e) {
      const status = e && typeof e === 'object' && 'status' in e ? Number((e as { status: number }).status) : 0
      if (status === 409) {
        setError('An active passport already exists. Revoke it before generating another.')
        await refresh()
      } else {
        setError(e instanceof Error ? e.message : 'Generation failed')
      }
    } finally {
      setBusy(false)
    }
  }

  async function revoke() {
    if (!passport?.passport_id) return
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      await postJson(`/income-passport/${passport.passport_id}/revoke?applicant_id=${encodeURIComponent(APPLICANT_ID)}`, {})
      setSuccess('Passport revoked. The public verification link will report revoked status.')
      setPassport(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Revoke failed')
    } finally {
      setBusy(false)
    }
  }

  function verificationUrl() {
    if (!passport?.verification_token) return ''
    return `${window.location.origin}/verify/income-passport/${passport.verification_token}`
  }

  async function copyLink() {
    const url = verificationUrl()
    if (!url) {
      setError('Verification token is only returned at generation time. Generate a new passport to copy a fresh link.')
      return
    }
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  function downloadPdf() {
    if (!passport?.passport_id) return
    window.open(
      apiUrl(`/income-passport/${passport.passport_id}/pdf?applicant_id=${encodeURIComponent(APPLICANT_ID)}`),
      '_blank',
      'noopener,noreferrer',
    )
  }

  function openPublic() {
    const url = verificationUrl()
    if (!url) {
      setError('Open the public page from a freshly generated passport (token is shown once).')
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  const income = passport?.snapshot?.income_summary
  const total = income?.total_verified_income_inr
  const avg = income?.average_monthly_income_inr
  const consistency = income?.income_consistency?.value as { label?: string } | undefined

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Income Passport"
        title="Share verified income — carefully."
        detail="One-page passport with classified aggregates. Public links never expose full statements or credentials."
        action={
          <div className="flex flex-wrap gap-2">
            <Button onClick={generate} disabled={busy}>{busy ? 'Working…' : 'Generate passport'}</Button>
            {passport && (
              <Button variant="ghost" onClick={revoke} disabled={busy}>Revoke</Button>
            )}
          </div>
        }
      />

      <Notice>
        Classifications distinguish fixture demo aggregates, linked PayPal aggregates, derived metrics, and missing fields.
        User-provided score inputs are not labelled as independently verified here.
      </Notice>
      {error && <Notice tone="error">{error}</Notice>}
      {success && <Notice tone="success">{success}</Notice>}

      {!passport ? (
        <GlassCard>
          <h2 className="font-semibold">No active passport</h2>
          <p className="mt-2 text-sm text-slate-500">
            Generate a passport for {APPLICANT_ID} to preview, download the PDF, and obtain a public verification link.
          </p>
        </GlassCard>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Reference"
              value={passport.passport_reference}
              detail={`Status · ${passport.integrity_status || passport.verification_status}`}
              icon={<Icon name="card" />}
            />
            <MetricCard
              label="Total income (12m)"
              value={total?.value != null ? money(Number(total.value), true) : 'Missing'}
              detail={String(total?.classification || 'missing')}
              icon={<Icon name="income" />}
              tone="gold"
            />
            <MetricCard
              label="Avg monthly"
              value={avg?.value != null ? money(Number(avg.value), true) : 'Missing'}
              detail={String(avg?.classification || 'missing')}
              icon={<Icon name="trend" />}
              tone="green"
            />
            <MetricCard
              label="Consistency"
              value={consistency?.label || 'Missing'}
              detail="Derived from monthly aggregates"
              icon={<Icon name="shield" />}
              tone="rose"
            />
          </div>

          <GlassCard>
            <h2 className="font-semibold">Passport status</h2>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div><dt className="text-xs text-slate-500">Issued</dt><dd>{passport.issued_at_utc}</dd></div>
              <div><dt className="text-xs text-slate-500">Expires</dt><dd>{passport.expires_at_utc}</dd></div>
              <div><dt className="text-xs text-slate-500">Verification method</dt><dd>{passport.snapshot?.verification.method}</dd></div>
              <div><dt className="text-xs text-slate-500">Evidence source</dt><dd>{passport.snapshot?.verification.evidence_source}</dd></div>
            </dl>
            {passport.snapshot?.verification.disclaimer && (
              <p className="mt-4 text-xs leading-relaxed text-slate-500">{passport.snapshot.verification.disclaimer}</p>
            )}

            <div className="mt-5 flex flex-wrap gap-2">
              <Button variant="ghost" onClick={downloadPdf}>Download PDF</Button>
              <Button variant="ghost" onClick={copyLink} disabled={!passport.verification_token}>
                {copied ? 'Copied' : 'Copy verification link'}
              </Button>
              <Button variant="ghost" onClick={openPublic} disabled={!passport.verification_token}>
                Open public page
              </Button>
            </div>
            {passport.verification_path && (
              <p className="mt-3 break-all rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-white/[.03]">
                {verificationUrl() || passport.verification_path}
              </p>
            )}
            {!passport.verification_token && (
              <p className="mt-3 text-xs text-amber-700">
                The raw verification token is returned only when a passport is generated in this session.
                Generate again (after revoke) to obtain a fresh shareable link.
              </p>
            )}
          </GlassCard>
        </>
      )}
    </div>
  )
}
