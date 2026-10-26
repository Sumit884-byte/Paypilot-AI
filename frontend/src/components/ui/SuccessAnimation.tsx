import { motion } from 'framer-motion'

export function SuccessAnimation({ onComplete }: { onComplete?: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.5 }}
      transition={{ type: 'spring', stiffness: 200, damping: 15 }}
      onAnimationComplete={onComplete}
      className="relative"
    >
      {/* Glowing ring */}
      <motion.div
        className="absolute inset-0 rounded-full bg-emerald-500"
        initial={{ scale: 1, opacity: 0.5 }}
        animate={{
          scale: [1, 1.3, 1],
          opacity: [0.5, 0.8, 0.5],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />
      {/* Main circle */}
      <motion.div
        className="relative grid h-24 w-24 place-items-center rounded-full bg-emerald-500 text-white shadow-glow"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.2, type: 'spring', stiffness: 200, damping: 15 }}
      >
        <motion.svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 0.4, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        >
          <motion.path d="M5 12l4 4L19 6" />
        </motion.svg>
      </motion.div>
      {/* Particles */}
      {[...Array(8)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute h-2 w-2 rounded-full bg-emerald-400"
          initial={{ x: 0, y: 0, scale: 0, opacity: 1 }}
          animate={{
            x: Math.cos((i * Math.PI) / 4) * 80,
            y: Math.sin((i * Math.PI) / 4) * 80,
            scale: [0, 1, 0],
            opacity: [1, 1, 0],
          }}
          transition={{
            delay: 0.5 + i * 0.05,
            duration: 1.2,
            ease: [0.22, 1, 0.36, 1],
          }}
          style={{
            left: '50%',
            top: '50%',
            marginLeft: '-4px',
            marginTop: '-4px',
          }}
        />
      ))}
    </motion.div>
  )
}
