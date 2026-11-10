import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'

interface Particle {
  id: number
  x: number
  y: number
  rotation: number
  scale: number
  color: string
  delay: number
}

const colors = ['#0070BA', '#009CDE', '#F5B942', '#003087', '#10B981', '#F59E0B']

// Fixed pseudo-random scatter, so rendering stays pure; each value is in [0, 1)
const scatter = (i: number, salt: number) => {
  const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
  return x - Math.floor(x)
}

const PARTICLES: Particle[] = Array.from({ length: 150 }, (_, i) => ({
  id: i,
  x: 50 + (scatter(i, 1) - 0.5) * 40,
  y: 50 + (scatter(i, 2) - 0.5) * 40,
  rotation: scatter(i, 3) * 360,
  scale: 0.5 + scatter(i, 4) * 0.5,
  color: colors[Math.floor(scatter(i, 5) * colors.length)],
  delay: scatter(i, 6) * 0.3,
}))

export function ConfettiBurst({ active }: { active: boolean }) {
  const burst = useMemo<Particle[]>(() => (active ? PARTICLES : []), [active])
  const [finished, setFinished] = useState<Particle[] | null>(null)
  const particles = finished === burst ? [] : burst

  useEffect(() => {
    if (!burst.length) return
    const timer = setTimeout(() => setFinished(burst), 3000)
    return () => clearTimeout(timer)
  }, [burst])

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 pointer-events-none"
        >
          {particles.map((p) => (
            <motion.div
              key={p.id}
              initial={{ x: '50%', y: '50%', rotate: 0, scale: 0, opacity: 1 }}
              animate={{
                x: `${p.x}%`,
                y: `${p.y}%`,
                rotate: p.rotation,
                scale: p.scale,
                opacity: 0,
              }}
              transition={{
                duration: 2.5,
                delay: p.delay,
                ease: [0.22, 1, 0.36, 1],
              }}
              className="absolute h-3 w-3 rounded-full"
              style={{ backgroundColor: p.color }}
            />
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
