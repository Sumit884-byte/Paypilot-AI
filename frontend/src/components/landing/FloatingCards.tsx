import { motion, useMotionValue, useSpring, useTransform, useReducedMotion } from 'framer-motion'
import type { MouseEvent } from 'react'
import { GlassCard } from '../ui/GlassCard'

export function FloatingCards() {
  const reduce = useReducedMotion()
  const mx = useMotionValue(0)
  const my = useMotionValue(0)
  const sx = useSpring(mx, { stiffness: 120, damping: 24 })
  const sy = useSpring(my, { stiffness: 120, damping: 24 })

  // Enhanced parallax with more dramatic movement and 3D depth
  const ax = useTransform(sx, [-50, 50], [-28, 28])
  const ay = useTransform(sy, [-50, 50], [-20, 20])
  const aScale = useTransform(sx, [-50, 50], [1.02, 1.08])
  const aRotateX = useTransform(sy, [-50, 50], [8, -8])
  const aRotateY = useTransform(sx, [-50, 50], [-8, 8])

  const bx = useTransform(sx, [-50, 50], [22, -22])
  const by = useTransform(sy, [-50, 50], [18, -18])
  const bScale = useTransform(sx, [-50, 50], [0.95, 1.05])
  const bRotateX = useTransform(sy, [-50, 50], [-6, 6])
  const bRotateY = useTransform(sx, [-50, 50], [6, -6])

  const cx = useTransform(sx, [-50, 50], [-12, 12])
  const cy = useTransform(sy, [-50, 50], [24, -24])
  const cScale = useTransform(sx, [-50, 50], [0.98, 1.02])
  const cRotateX = useTransform(sy, [-50, 50], [4, -4])
  const cRotateY = useTransform(sx, [-50, 50], [-4, 4])

  function onMove(event: MouseEvent<HTMLDivElement>) {
    if (reduce) return
    const rect = event.currentTarget.getBoundingClientRect()
    mx.set(((event.clientX - rect.left) / rect.width - 0.5) * 100)
    my.set(((event.clientY - rect.top) / rect.height - 0.5) * 100)
  }

  return (
    <div
      onMouseMove={onMove}
      onMouseLeave={() => {
        mx.set(0)
        my.set(0)
      }}
      className="relative mx-auto h-[420px] w-full max-w-lg lg:h-[500px]"
      style={{ perspective: '1000px' }}
    >
      <motion.div
        style={{
          x: reduce ? 0 : ax,
          y: reduce ? 0 : ay,
          scale: reduce ? 1 : aScale,
          rotateX: reduce ? 0 : aRotateX,
          rotateY: reduce ? 0 : aRotateY,
          transformStyle: 'preserve-3d',
        }}
        className="absolute left-2 top-6 w-[78%] animate-float sm:left-8"
      >
        <GlassCard interactive={false} className="p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-paypal">PayScore</p>
          <p className="mt-2 font-display text-5xl font-bold tracking-tight">731</p>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Low risk · Priya, jewellery seller</p>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: '79%' }}
              transition={{ delay: 0.4, duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
              className="h-full rounded-full bg-gradient-to-r from-paypal to-amber-glow"
            />
          </div>
        </GlassCard>
      </motion.div>

      <motion.div
        style={{
          x: reduce ? 0 : bx,
          y: reduce ? 0 : by,
          scale: reduce ? 1 : bScale,
          rotateX: reduce ? 0 : bRotateX,
          rotateY: reduce ? 0 : bRotateY,
          transformStyle: 'preserve-3d',
        }}
        className="absolute right-0 top-36 w-[70%] sm:right-2"
      >
        <GlassCard interactive={false} className="p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">12-month PayPal income</p>
          <p className="mt-1 text-2xl font-bold">₹16.5L</p>
          <svg viewBox="0 0 160 48" className="mt-3 h-12 w-full">
            <motion.path
              d="M2 36 C 20 34, 28 22, 44 24 S 70 40, 88 18 S 120 8, 158 14"
              fill="none"
              stroke="#0070BA"
              strokeWidth="3"
              strokeLinecap="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.4, delay: 0.3 }}
            />
          </svg>
        </GlassCard>
      </motion.div>

      <motion.div
        style={{
          x: reduce ? 0 : cx,
          y: reduce ? 0 : cy,
          scale: reduce ? 1 : cScale,
          rotateX: reduce ? 0 : cRotateX,
          rotateY: reduce ? 0 : cRotateY,
          transformStyle: 'preserve-3d',
        }}
        className="absolute bottom-2 left-4 w-[68%] sm:left-10"
      >
        <GlassCard interactive={false} className="flex items-center gap-3 p-4">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-paypal/15 text-lg text-paypal">
            ◉
          </span>
          <div>
            <p className="text-sm font-semibold">Income copilot live</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Fixture + sandbox history</p>
          </div>
        </GlassCard>
      </motion.div>
    </div>
  )
}
