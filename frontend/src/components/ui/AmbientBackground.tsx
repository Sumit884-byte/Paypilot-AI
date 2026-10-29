export function AmbientBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden bg-[rgb(var(--bg))]" aria-hidden />
  )
}
