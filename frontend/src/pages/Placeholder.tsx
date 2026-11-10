import { motion } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Skeleton } from '../components/ui/Skeleton'
import { fadeUp, stagger } from '../lib/motion'

export function Placeholder({ title, endpoint }: { title: string; endpoint: string }) {
  return (
    <motion.div variants={stagger} initial="initial" animate="animate" className="space-y-5">
      <motion.div variants={fadeUp}>
        <h1 className="font-display text-3xl font-bold">{title}</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Wired to {endpoint} in a later slice.</p>
      </motion.div>
      <motion.div variants={fadeUp}>
        <GlassCard interactive={false} className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-40" />
          <Skeleton className="h-8 w-full" />
        </GlassCard>
      </motion.div>
    </motion.div>
  )
}
