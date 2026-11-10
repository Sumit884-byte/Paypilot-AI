import { motion } from 'framer-motion'
import { useTheme } from '../../context/ThemeContext'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  const dark = theme === 'dark'

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="relative h-9 w-[3.85rem] rounded-full border border-navy-900/10 bg-white/55 p-1 shadow-inner backdrop-blur dark:border-white/10 dark:bg-navy-800"
    >
      <motion.span
        layout
        className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-paypal to-paypal-dark text-[13px] text-white shadow-glow"
        animate={{ x: dark ? 22 : 0 }}
        transition={{ type: 'spring', stiffness: 420, damping: 28 }}
      >
        {dark ? '☾' : '☀'}
      </motion.span>
    </button>
  )
}
