const explicit = import.meta.env.VITE_PAYSCORE_API_URL?.replace(/\/$/, '') ?? ''

/** Empty during local development so Vite's proxy keeps requests same-origin. */
export const API_BASE = explicit

export function apiUrl(path: string) {
  const normalised = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE}${normalised}`
}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = typeof body?.detail === 'string'
      ? body.detail
      : typeof body?.error === 'string'
        ? body.error.replaceAll('_', ' ')
        : `Request failed (${response.status})`
    throw new ApiError(message, response.status, body)
  }
  return body as T
}

export const postJson = <T>(path: string, body: unknown) =>
  apiRequest<T>(path, { method: 'POST', body: JSON.stringify(body) })

export async function postForm<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(apiUrl(path), { method: 'POST', body })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = typeof payload?.detail === 'string'
      ? payload.detail
      : typeof payload?.error === 'string'
        ? payload.error.replaceAll('_', ' ')
        : `Request failed (${response.status})`
    throw new ApiError(message, response.status, payload)
  }
  return payload as T
}

export const paypalLoginUrl = () => apiUrl('/paypal/auth/login')

export type PaypalStatus =
  | { paypal: 'ok'; mode: string; api_base: string; client_id: string }
  | { paypal: 'unavailable'; code: string; detail: string }

export async function fetchPaypalStatus(): Promise<PaypalStatus> {
  return apiRequest<PaypalStatus>('/paypal/status')
}

export type Persona = {
  persona_id: string
  display_name: string
  profile: { city?: string; business_type?: string; description?: string }
  scenario: { headline?: string; requested_amount_inr: number; requested_term_months: number; narrative?: string }
  model_input: Record<string, number | string | null>
  monthly_summary: Array<{ month: string; sales_inr: number; refunds_inr: number; net_revenue_inr: number; sale_count: number }>
  recent_transactions: Array<{ txn_id: string; date: string; type: string; amount_inr: number; category: string; status: string }>
  synthetic: boolean
}

export const money = (amount: number, compact = false) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: compact ? 0 : 2,
    notation: compact ? 'compact' : 'standard' }).format(Number.isFinite(amount) ? amount : 0)

export const percent = (ratio: number) => `${(Math.max(0, ratio) * 100).toFixed(1)}%`

export const isDemoApplicant = (applicantId: string) => applicantId.startsWith('PSC-')
