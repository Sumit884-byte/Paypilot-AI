import { useAuth } from '../../context/AuthContext'
import { DEMO_PERSONAS, useActivePersona } from '../../lib/personas'

/** Demo-only toggle between the sandbox personas. Switching clears the previous persona's workspace state. */
export function PersonaSwitch() {
  const { session, enterDemo } = useAuth()
  const active = useActivePersona()
  if (!session?.demo) return null

  return (
    <div role="group" aria-label="Demo persona" className="flex rounded-full bg-slate-100 p-0.5 text-[11px] font-semibold dark:bg-white/10">
      {Object.values(DEMO_PERSONAS).map((p) => (
        <button
          key={p.key}
          type="button"
          aria-pressed={active.key === p.key}
          onClick={() => active.key !== p.key && enterDemo(p.key)}
          className={`whitespace-nowrap rounded-full px-2.5 py-1 transition-colors ${
            active.key === p.key ? 'bg-white text-paypal shadow-sm dark:bg-navy-900' : 'text-slate-600 hover:text-paypal dark:text-slate-300'
          }`}
        >
          {p.key === 'priya' ? p.firstName : <><span className="sm:hidden">Risky</span><span className="hidden sm:inline">Risky borrower</span></>}
        </button>
      ))}
    </div>
  )
}
