import { motion } from 'framer-motion'
import { NavLink, useLocation } from 'react-router-dom'
import { SandboxBadge } from '../ui/SandboxBadge'
import { KeyboardShortcutsHint } from '../ui/Workspace'
import { cn } from '../../lib/cn'

const links = [
  { to: '/app', label: 'Overview', icon: OverviewIcon, end: true },
  { to: '/app/income', label: 'Income', icon: IncomeIcon },
  { to: '/app/score', label: 'PayScore', icon: ScoreIcon },
  { to: '/app/offer-guard', label: 'Offer guard', icon: ShieldIcon },
  { to: '/app/copilot', label: 'AI copilot', icon: CopilotIcon },
  { to: '/app/repay', label: 'Repayment', icon: RepayIcon },
  { to: '/app/cockpit', label: 'AG Studio', icon: CockpitIcon },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const location = useLocation()

  return (
    <aside className="flex h-full min-h-svh flex-col gap-5 p-3">
      <div className="flex h-9 items-center gap-2 px-2 text-xs font-semibold text-slate-200">
        <span className="grid h-6 w-6 place-items-center rounded-md text-amber-300" aria-hidden="true">✣</span>
        Personal workspace
      </div>
      <nav className="relative flex flex-1 flex-col gap-1">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'relative z-10 flex items-center gap-3 rounded-lg px-2.5 py-2 text-xs font-medium transition-colors',
                isActive
                  ? 'text-navy-950 dark:text-white'
                  : 'text-slate-500 hover:text-navy-900 dark:text-slate-400 dark:hover:text-white',
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    layoutId="sidebar-active"
                    className="absolute inset-0 -z-10 rounded-lg bg-paypal/15 ring-1 ring-paypal/50"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                <link.icon active={isActive || location.pathname === link.to} />
                {link.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-white/[.07] pt-3">
        <KeyboardShortcutsHint />
      </div>
      <SandboxBadge className="justify-start text-[10px]" />
    </aside>
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


