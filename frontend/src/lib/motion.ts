import type { Variants } from 'framer-motion'

export const easeOutExpo = [0.22, 1, 0.36, 1] as const

export const pageFade: Variants = {
  initial: { opacity: 0, y: 18, filter: 'blur(6px)' },
  animate: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.42, ease: easeOutExpo },
  },
  exit: {
    opacity: 0,
    y: -12,
    filter: 'blur(4px)',
    transition: { duration: 0.22 },
  },
}

export const stagger: Variants = {
  initial: {},
  animate: {
    transition: { staggerChildren: 0.08, delayChildren: 0.05 },
  },
}

export const fadeUp: Variants = {
  initial: { opacity: 0, y: 20 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.48, ease: easeOutExpo },
  },
}

export const hoverLift: Variants = {
  rest: { y: 0, scale: 1 },
  hover: {
    y: -5,
    scale: 1.015,
    transition: { type: 'spring', stiffness: 380, damping: 24 },
  },
}
