import { cn } from '../../lib/cn'

export function SandboxBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border border-amber-glow/45 bg-amber-glow/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-800 dark:text-amber-glow',
        className,
      )}
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-glow shadow-glow-gold" />
      sandbox only — no real lending
    </span>
  )
}
