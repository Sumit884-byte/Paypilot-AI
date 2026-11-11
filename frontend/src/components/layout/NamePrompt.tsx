import { useState, type FormEvent } from 'react'
import { useAuth } from '../../context/AuthContext'
import { Button } from '../ui/Button'
import { GlassCard } from '../ui/GlassCard'
import { inputClass } from '../ui/Workspace'

/** After a real PayPal link, ask what to call the user. PayPal sign-in deliberately shares no name with the app. */
export function NamePrompt() {
  const { session, setDisplayName } = useAuth()
  const [name, setName] = useState('')
  if (!session?.linked || session.demo || session.displayName !== undefined) return null

  function save(e: FormEvent) {
    e.preventDefault()
    if (name.trim()) setDisplayName(name)
  }

  return (
    <GlassCard interactive={false} className="mb-6 p-5">
      <form onSubmit={save} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex-1 space-y-2">
          <span className="block text-sm font-semibold">Your PayPal account is linked. What should we call you?</span>
          <span className="block text-xs text-slate-500">
            PayPal doesn't share your name with Paypilot, so it stays in this browser only.
          </span>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            maxLength={60}
            aria-label="Your name"
            className={inputClass}
          />
        </label>
        <div className="flex gap-2">
          <Button type="submit" disabled={!name.trim()}>Save</Button>
          <Button type="button" variant="ghost" onClick={() => setDisplayName('')}>Not now</Button>
        </div>
      </form>
    </GlassCard>
  )
}
