import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

type Props = {
  children: ReactNode
  className?: string
  variant?: 'primary' | 'ghost' | 'gold'
  type?: 'button' | 'submit' | 'reset'
  onClick?: () => void
  disabled?: boolean
}

export function Button({
  className,
  variant = 'primary',
  children,
  type = 'button',
  onClick,
  disabled,
}: Props) {
  const styles = {
    primary: 'bg-paypal text-white shadow-glow hover:bg-paypal-light',
    ghost:
      'bg-white/40 text-current border border-navy-900/10 hover:bg-white/70 dark:bg-white/5 dark:border-white/10 dark:hover:bg-white/10',
    gold: 'bg-amber-glow text-navy-950 shadow-glow-gold hover:brightness-110',
  }[variant]

  return (
    <motion.button
      whileHover={disabled ? undefined : { y: -2, scale: 1.02 }}
      whileTap={disabled ? undefined : { scale: 0.98 }}
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-2xl px-5 py-2.5 text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-55',
        styles,
        className,
      )}
    >
      {children}
    </motion.button>
  )
}
