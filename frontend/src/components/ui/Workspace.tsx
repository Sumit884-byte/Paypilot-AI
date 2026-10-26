import { useEffect, useState, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { GlassCard } from './GlassCard'

export function PageHeading({ eyebrow, title, detail, action }: {
  eyebrow: string; title: string; detail: string; action?: ReactNode
}) {
  return (
    <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[.24em] text-paypal">{eyebrow}</p>
        <h1 className="mt-2 font-display text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">{detail}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

export function MetricCard({ label, value, detail, icon, tone = 'blue', delay = 0 }: {
  label: string; value: ReactNode; detail: string; icon: ReactNode; tone?: 'blue' | 'gold' | 'green' | 'rose'; delay?: number
}) {
  const tones = { blue: 'text-paypal bg-paypal/10', gold: 'text-amber-600 bg-amber-400/15',
    green: 'text-emerald-500 bg-emerald-400/15', rose: 'text-rose-500 bg-rose-400/15' }
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: .42 }}>
      <GlassCard className="h-full p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
            <p className="mt-3 font-display text-2xl font-bold tracking-tight sm:text-[1.7rem]">{value}</p>
          </div>
          <span className={`flex h-10 w-10 items-center justify-center rounded-2xl ${tones[tone]}`}>{icon}</span>
        </div>
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{detail}</p>
      </GlassCard>
    </motion.div>
  )
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'success' | 'warning' | 'error' }) {
  const cls = { info: 'border-paypal/20 bg-paypal/5 text-slate-600 dark:text-slate-300',
    success: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    warning: 'border-amber-500/25 bg-amber-400/10 text-amber-800 dark:text-amber-200',
    error: 'border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300' }
  return <div role="status" className={`rounded-2xl border px-4 py-3 text-sm leading-relaxed ${cls[tone]}`}>{children}</div>
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="block space-y-2"><span className="text-xs font-semibold text-slate-600 dark:text-slate-300">{label}</span>
    {children}{hint && <span className="block text-[11px] text-slate-500">{hint}</span>}</label>
}

export const inputClass = 'w-full rounded-2xl border border-slate-200/80 bg-white/70 px-4 py-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-paypal/50 focus:ring-4 focus:ring-paypal/10 dark:border-white/10 dark:bg-white/[.035] dark:text-white'

export function CountUp({ to, decimals = 0, prefix = '', suffix = '' }: { to: number; decimals?: number; prefix?: string; suffix?: string }) {
  const reduce = useReducedMotion()
  const [value, setValue] = useState(reduce ? to : 0)
  useEffect(() => {
    if (reduce) { setValue(to); return }
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 850)
      const eased = 1 - (1 - progress) ** 4
      setValue(to * eased)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [reduce, to])
  return <>{prefix}{value.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</>
}

export function ProgressRing({ value, size = 136, stroke = 11, label, sublabel }: {
  value: number; size?: number; stroke?: number; label: ReactNode; sublabel?: string
}) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const progress = Math.max(0, Math.min(1, value))
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }} aria-label={`${Math.round(progress * 100)} percent`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="currentColor" strokeWidth={stroke} className="text-slate-200 dark:text-white/10" />
        <motion.circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="url(#ringGlow)" strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circumference} initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - progress) }} transition={{ duration: 1.2, ease: [.22, 1, .36, 1] }} />
        <defs><linearGradient id="ringGlow"><stop stopColor="#0070BA" /><stop offset="1" stopColor="#F5B942" /></linearGradient></defs>
      </svg>
      <div className="absolute text-center"><div className="font-display text-3xl font-bold">{label}</div>{sublabel && <div className="mt-1 text-[10px] uppercase tracking-widest text-slate-500">{sublabel}</div>}</div>
    </div>
  )
}

export function Icon({ name, size = 18, className = '' }: { name: string; size?: number; className?: string }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, className, 'aria-hidden': true as const }
  const paths: Record<string, ReactNode> = {
    spark: <><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></>,
    income: <><path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 6-7"/><path d="M16 6h4v4"/></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/></>,
    trend: <><path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    arrow: <><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></>,
    chat: <><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/></>,
    card: <><rect x="2" y="5" width="20" height="14" rx="3"/><path d="M2 10h20"/><path d="M6 15h4"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    upload: <><path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M4 20h16"/></>,
    menu: <><path d="M4 6h16M4 12h16M4 18h16"/></>,
  }
  return <svg {...common}>{paths[name] ?? paths.spark}</svg>
}

export function PulseDot({ className = '' }: { className?: string }) {
  return <span className={`relative flex h-2.5 w-2.5 ${className}`}><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50 motion-reduce:animate-none"/><span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"/></span>
}

export function Divider({ className = '' }: { className?: string }) {
  return <div className={`h-px w-full bg-slate-200/70 dark:bg-white/10 ${className}`} />
}

// Toast / limit-violation popup
export function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      transition={{ duration: 0.2 }}
      className="fixed top-6 right-6 z-50 rounded-2xl border border-rose-500/40 bg-rose-500/10 px-5 py-4 shadow-glass-lg flex items-center gap-3 animate-in"
    >
      <span className="text-rose-500">⚠</span>
      <div className="flex flex-col">
        <p className="text-sm font-semibold text-rose-400 dark:text-rose-300">Limit exceeded</p>
        <p className="text-xs text-slate-500 dark:text-slate-400">{message}</p>
      </div>
      <button
        onClick={onDismiss}
        className="ml-auto p-1 hover:bg-rose-500/20 rounded"
        aria-label="Dismiss"
      >
        <Icon name="menu" size={14} />
      </button>
    </motion.div>
  )
}

// Keyboard shortcuts helper
export function useKeyboardShortcut(key: string, callback: () => void, meta = true) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((meta && (e.metaKey || e.ctrlKey)) || (!meta && !e.metaKey && !e.ctrlKey)) {
        if (e.key.toLowerCase() === key.toLowerCase() && !e.shiftKey && !e.altKey) {
          const target = e.target as HTMLElement
          if (!target.closest('input, textarea, [contenteditable="true"]')) {
            e.preventDefault()
            callback()
          }
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [key, callback, meta])
}

export function KeyboardShortcutsHint() {
  const isMac = typeof navigator !== 'undefined' && navigator.platform.toUpperCase().indexOf('MAC') >= 0
  const mod = isMac ? '⌘' : 'Ctrl'
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
      <kbd className="inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-white/10 px-2 py-0.5 font-mono text-[10px] border border-slate-200 dark:border-white/10">
        {mod}
      </kbd>
      <kbd className="inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-white/10 px-2 py-0.5 font-mono text-[10px] border border-slate-200 dark:border-white/10">
        K
      </kbd>
      <span>Focus copilot</span>
      <span className="mx-1">·</span>
      <kbd className="inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-white/10 px-2 py-0.5 font-mono text-[10px] border border-slate-200 dark:border-white/10">
        {mod}
      </kbd>
      <kbd className="inline-flex items-center gap-1 rounded bg-slate-100 dark:bg-white/10 px-2 py-0.5 font-mono text-[10px] border border-slate-200 dark:border-white/10">
        /
      </kbd>
      <span>Shortcuts</span>
    </div>
  )
}
