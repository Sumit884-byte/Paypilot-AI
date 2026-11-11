import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { NavLink, useLocation } from 'react-router-dom'
import { cn } from '../../lib/cn'
import { useActivePersona } from '../../lib/personas'

const links = [
  { to: '/app', label: 'Overview', icon: OverviewIcon, end: true },
  { to: '/app/income', label: 'Income', icon: IncomeIcon },
  { to: '/app/score', label: 'PayScore', icon: ScoreIcon },
  { to: '/app/model-card', label: 'Model card', icon: ModelCardIcon },
  { to: '/app/passport', label: 'Passport', icon: PassportIcon },
  { to: '/app/negotiate', label: 'Negotiate', icon: NegotiateIcon },
  { to: '/app/offer-guard', label: 'Offer guard', icon: ShieldIcon },
  { to: '/app/copilot', label: 'AI copilot', icon: CopilotIcon },
  { to: '/app/repay', label: 'Repayment', icon: RepayIcon },
  { to: '/app/cockpit', label: 'AG Studio', icon: CockpitIcon },
]

export function Sidebar() {
  const location = useLocation()
  const persona = useActivePersona()
  const tabsRef = useRef<HTMLDivElement>(null)

  // The tab row scrolls sideways on phones; keep the active tab visible after navigation
  useEffect(() => {
    tabsRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [location.pathname])

  return (
    <nav aria-label="Main navigation" className="border-b border-[rgb(var(--line))] bg-[rgb(var(--surface))]">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-5 px-4 sm:px-6 lg:px-10">
        <div ref={tabsRef} className="flex min-w-0 flex-1 gap-1 overflow-x-auto py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              cn(
                'relative z-10 flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-xs font-medium transition-colors',
                isActive
                  ? 'bg-sky-50 text-paypal'
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900',
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    layoutId="sidebar-active"
                    className="absolute inset-0 -z-10 rounded-full bg-sky-50"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                <link.icon active={isActive || location.pathname === link.to} />
                {link.label}
              </>
            )}
          </NavLink>
        ))}
        </div>
        <div className="hidden shrink-0 items-center gap-2 py-2 text-[11px] text-slate-600 md:flex">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-amber-50 font-semibold text-amber-800">{persona.initial}</span>
          <span>{persona.linked ? `${persona.firstName || 'You'} · PayPal account` : `${persona.firstName} · ${persona.applicantId}`}</span>
        </div>
      </div>
    </nav>
  )
}

function OverviewIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}>
      <path fill="currentColor" d="M4 13h6v7H4v-7zm10-9h6v16h-6V4zM4 4h6v7H4V4zm10 9h6v7h-6v-7z" />
    </svg>
  )
}

function ScoreIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}>
      <path fill="currentColor" d="M12 3a9 9 0 1 0 9 9h-2a7 7 0 1 1-7-7V3zm1 5v4.4l3.2 1.9-.9 1.5L11 13V8h2z" />
    </svg>
  )
}

function IncomeIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}>
      <path fill="currentColor" d="M3 18h18v2H3v-2zm2-3 4-5 3 4 4-6 4 7H5z" />
    </svg>
  )
}


function RepayIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}>
      <path fill="currentColor" d="M12 2a10 10 0 1 0 10 10h-2A8 8 0 1 1 12 4V2zm1 5v5l4 2-.7 1.3L11 13V7h2z" />
    </svg>
  )
}

function ShieldIcon({ active }: { active: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}><path fill="currentColor" d="M12 2 20 5v6c0 5.4-3.4 9.3-8 11-4.6-1.7-8-5.6-8-11V5l8-3Zm0 3.1L7 7v4c0 3.7 2 6.5 5 7.9 3-1.4 5-4.2 5-7.9V7l-5-1.9Zm-1 8.3-2-2 1.4-1.4 1.3 1.3 2.9-2.9L16 9.8l-4.3 4.3L11 13.4Z" /></svg>
}

function CopilotIcon({ active }: { active: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}><path fill="currentColor" d="M12 2 14 8l6 2-6 2-2 6-2-6-6-2 6-2 2-6Zm7 13 1.1 2.9L23 19l-2.9 1.1L19 23l-1.1-2.9L15 19l2.9-1.1L19 15ZM5 2l.8 2.2L8 5l-2.2.8L5 8l-.8-2.2L2 5l2.2-.8L5 2Z" /></svg>
}

function CockpitIcon({ active }: { active: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}><path fill="currentColor" d="M3 3h8v8H3V3Zm10 0h8v5h-8V3ZM13 10h8v11h-8V10ZM3 13h8v8H3v-8Z" /></svg>
}

function ModelCardIcon({ active }: { active: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}><path fill="currentColor" d="M4 4h16v4H4V4Zm0 6h10v2H4v-2Zm0 4h16v2H4v-2Zm0 4h10v2H4v-2Z" /></svg>
}

function PassportIcon({ active }: { active: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}><path fill="currentColor" d="M6 2h9l5 5v15a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm8 1.5V8h4.5L14 3.5ZM8 12h8v2H8v-2Zm0 4h8v2H8v-2Z" /></svg>
}

function NegotiateIcon({ active }: { active: boolean }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" className={active ? 'text-paypal' : 'opacity-70'}><path fill="currentColor" d="M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm12.5 1.5L14 17l2.5 2.5L19 17l-2.5-2.5Z" /></svg>
}


