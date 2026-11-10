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
  return isDemoPersonaKey(session?.persona) ? DEMO_PERSONAS[session.persona] : DEMO_PERSONAS.priya
}
