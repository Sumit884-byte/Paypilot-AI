import { motion } from 'framer-motion'

function PayPalMark() {
  return (
    <svg width="22" height="26" viewBox="0 0 24 28" aria-hidden>
      <path
        d="M19.5 7.2c-.3 2.1-1.4 3.6-3.2 4.6-1.2.6-2.6.9-4.1.9H9.8l-.8 5.1H6.3L8.8 2.4h6.2c1.9 0 3.3.5 4.1 1.5.6.7.8 1.6.4 3.3z"
        fill="#003087"
      />
      <path
        d="M21.2 7c-.4 2.5-1.7 4.3-3.8 5.4-1.4.7-3.1 1-5 1h-2.7L8.5 20.8H5.7L8.4 3.7h6.6c2.2 0 3.8.6 4.8 1.7.8.9 1.1 2.1.4 3.6z"
        fill="#009CDE"
      />
      <path
        d="M9.9 12.7h2.4c1.5 0 2.9-.3 4.1-.9 1.8-1 2.9-2.5 3.2-4.6.3-1.6.1-2.6-.4-3.3C18.3 2.9 16.9 2.4 15 2.4H8.8L6.3 17.6h2.7l.9-5z"
        fill="#012169"
      />
    </svg>
  )
}

type Props = {
  onClick: () => void
  busy?: boolean
}

export function PayPalLoginButton({ onClick, busy }: Props) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={busy}
      whileHover={{ y: -3, boxShadow: '0 14px 32px rgba(255, 196, 57, 0.5)' }}
      whileTap={{ scale: 0.985 }}
      className="group relative inline-flex h-14 min-w-[260px] items-center justify-center gap-3 overflow-hidden rounded-[28px] bg-[#FFC439] px-7 text-[17px] font-semibold text-[#003087] shadow-[0_8px_24px_rgba(255,196,57,0.35)] disabled:opacity-70"
    >
      <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/50 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
      <span className="absolute inset-0 rounded-[28px] ring-1 ring-black/5" />
      <PayPalMark />
      <span>{busy ? 'Connecting…' : 'Log in with PayPal'}</span>
    </motion.button>
  )
}
