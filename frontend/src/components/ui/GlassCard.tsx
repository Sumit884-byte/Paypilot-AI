import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'
import { hoverLift } from '../../lib/motion'

type Props = {
  className?: string
  interactive?: boolean
  children: ReactNode
}

export function GlassCard({ className, interactive = true, children }: Props) {
  return (
    <motion.div
      initial="rest"
      whileHover={interactive ? 'hover' : undefined}
      variants={interactive ? hoverLift : undefined}
      className={cn('glass rounded-lg p-4 sm:p-5', className)}
    >
      {children}
    </motion.div>
  )
}
