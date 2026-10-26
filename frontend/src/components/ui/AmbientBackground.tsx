export function AmbientBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <div className="absolute inset-0 bg-mesh-light dark:bg-mesh-dark" />
      <div className="grid-fade opacity-70 dark:opacity-100" />
      <div className="grain" />
      <div className="absolute left-[-12%] top-[-18%] h-[32rem] w-[32rem] rounded-full bg-paypal/30 blur-[90px] animate-pulseGlow dark:bg-paypal/25" />
      <div className="absolute right-[-10%] top-[12%] h-[26rem] w-[26rem] rounded-full bg-amber-glow/25 blur-[88px] animate-pulseGlow" />
      <div className="absolute bottom-[-20%] left-[28%] h-[22rem] w-[22rem] rounded-full bg-paypal-light/20 blur-[80px]" />
    </div>
  )
}
