import { motion, AnimatePresence } from 'framer-motion'
import { useEffect, useState } from 'react'

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

export function ConfettiBurst({ active }: { active: boolean }) {
  const [particles, setParticles] = useState<Particle[]>([])

  useEffect(() => {
    if (active) {
      const newParticles: Particle[] = Array.from({ length: 150 }, (_, i) => ({
        id: i,
        x: 50 + (Math.random() - 0.5) * 40,
        y: 50 + (Math.random() - 0.5) * 40,
        rotation: Math.random() * 360,
        scale: 0.5 + Math.random() * 0.5,
        color: colors[Math.floor(Math.random() * colors.length)],
        delay: Math.random() * 0.3,
      }))
      setParticles(newParticles)

      const timer = setTimeout(() => setParticles([]), 3000)
      return () => clearTimeout(timer)
    }
  }, [active])

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
