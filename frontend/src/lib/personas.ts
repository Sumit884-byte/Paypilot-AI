import { useAuth } from '../context/AuthContext'

/** Synthetic sandbox personas for judge demo mode. Values mirror fixtures/personas/*.json. */
export type DemoPersona = {
  key: 'priya' | 'rohan'
  applicantId: string
  name: string
  firstName: string
  initial: string
  tagline: string
  email: string
  paypalDemoId: string
  requestedAmountInr: number
  requestedTermMonths: number
  /** True for a real PayPal-linked user: names come from them, not from a demo persona */
  linked?: boolean
}

export const DEMO_PERSONAS: Record<DemoPersona['key'], DemoPersona> = {
  priya: {
    key: 'priya',
    applicantId: 'PSC-PRIYA-001',
    name: 'Priya Nair',
    firstName: 'Priya',
    initial: 'P',
    tagline: 'Stable online seller',
    email: 'priya@example.test',
    paypalDemoId: 'DEMO-PRIYA',
    requestedAmountInr: 400000,
    requestedTermMonths: 18,
  },
  rohan: {
    key: 'rohan',
    applicantId: 'PSC-ROHAN-003',
    name: 'Rohan Kulkarni',
    firstName: 'Rohan',
    initial: 'R',
    tagline: 'Risky borrower',
    email: 'rohan@example.test',
    paypalDemoId: 'DEMO-ROHAN',
    requestedAmountInr: 600000,
    requestedTermMonths: 36,
  },
}

export const isDemoPersonaKey = (value: string | undefined): value is DemoPersona['key'] =>
  value === 'priya' || value === 'rohan'

export function useActivePersona(): DemoPersona {
  const { session } = useAuth()
  const base = isDemoPersonaKey(session?.persona) ? DEMO_PERSONAS[session.persona] : DEMO_PERSONAS.priya
  if (!session?.linked || session.demo) return base
  // A real PayPal user: never show a demo persona's name. The applicant id still drives the demo scoring calls.
  const name = session.displayName || ''
  return { ...base, name, firstName: name.split(' ')[0] || '', initial: (name[0] || 'Y').toUpperCase(),
           tagline: 'PayPal account', linked: true }
}
