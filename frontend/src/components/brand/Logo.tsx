import { motion, useReducedMotion } from 'framer-motion'
import { cn } from '../../lib/cn'

export function Wordmark({ compact = false, className }: { compact?: boolean; className?: string }) {
  const reduce = useReducedMotion()
  const letters = 'Paypilot'.split('')

  return (
    <span className={cn('inline-flex min-w-0 items-baseline gap-1.5 font-display tracking-tight', className)}>
      <span className="inline-flex whitespace-nowrap">
        {letters.map((letter, index) => (
          <motion.span
            key={`${letter}-${index}`}
            initial={{ opacity: 0, y: 12, rotate: -3 }}
            animate={{
              opacity: 1,
              y: 0,
              rotate: 0,
            }}
            whileHover={{ scale: 1.1, color: '#0070BA' }}
            transition={{
              delay: reduce ? 0 : 0.025 * index,
              duration: 0.48,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="text-lg font-extrabold text-navy-950 dark:text-white sm:text-xl"
          >
            {letter}
          </motion.span>
        ))}
      </span>
      <motion.span
        initial={{ opacity: 0, scale: 0.5, rotate: -12, x: -10 }}
        animate={{
          opacity: 1,
          scale: 1,
          rotate: 0,
          x: 0,
        }}
        whileHover={{ scale: 1.15, rotate: 3 }}
        whileTap={{ scale: 0.95 }}
        transition={{
          delay: reduce ? 0 : 0.28,
          type: 'spring',
          stiffness: 360,
          damping: 18,
        }}
        className="rounded-md bg-gradient-to-r from-paypal to-paypal-light px-1.5 py-0.5 text-[11px] font-extrabold uppercase tracking-[0.18em] text-white shadow-glow"
      >
        AI
      </motion.span>
      {!compact && (
        <motion.span
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: reduce ? 0 : 0.4, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="hidden text-[11px] font-medium uppercase tracking-[0.2em] text-slate-500 sm:inline dark:text-slate-400"
        >
          copilot
        </motion.span>
      )}
    </span>
  )
}

export function Mark({ className = 'h-9 w-9' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <defs>
        <linearGradient id="pp-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#009CDE" />
          <stop offset="55%" stopColor="#0070BA" />
          <stop offset="100%" stopColor="#F5B942" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#pp-mark)" />
      <path
        d="M12 28V12.5h8.4c3.6 0 5.8 1.9 5.8 4.8 0 3.2-2.4 5-5.9 5H16.6V28H12zm4.6-9.3h3.3c1.6 0 2.5-.8 2.5-2.1 0-1.2-.8-2-2.5-2h-3.3v4.1z"
        fill="white"
      />
    </svg>
  )
}

export function Logo({ compact = false }: { compact?: boolean }) {
  const reduce = useReducedMotion()

  return (
    <span className="inline-flex items-center gap-2.5">
      <div className="relative">
        <motion.span
          initial={{ rotate: -12, scale: 0.85, opacity: 0 }}
          animate={{
            rotate: 0,
            scale: 1,
            opacity: 1,
          }}
          whileHover={{ rotate: 8, scale: 1.05 }}
          transition={{ type: 'spring', stiffness: 280, damping: 16 }}
        >
          <Mark />
        </motion.span>
        {!reduce && (
          <motion.span
            className="absolute inset-0 rounded-[12px] pointer-events-none"
            animate={{
              boxShadow: [
                '0 0 20px rgba(0, 112, 186, 0.4)',
                '0 0 40px rgba(0, 112, 186, 0.6)',
                '0 0 20px rgba(0, 112, 186, 0.4)',
              ],
            }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
          />
        )}
      </div>
      <Wordmark compact={compact} />
    </span>
  )
}
