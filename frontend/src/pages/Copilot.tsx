import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { GlassCard } from '../components/ui/GlassCard'
import { Button } from '../components/ui/Button'
import { Icon, inputClass, Notice, PageHeading, PulseDot, useKeyboardShortcut } from '../components/ui/Workspace'
import { postJson } from '../lib/api'

type Message = {
  from: 'you' | 'agent'
  text: string
  tools?: Array<{ label: string; status?: string }>
  analysis?: { kind?: string; result?: { status?: string; recommended_percentage?: number | null } }
  approval?: {
    required: boolean
    action: string
    amount?: number
    details?: string
  }
  approved?: boolean
}

const applicant = 'PSC-PRIYA-001'

const SUGGESTED_QUESTIONS = [
  'Can I afford ₹50k?',
  'What\'s my income trend?',
  'How does my PayScore compare?',
  'Should I take this loan offer?',
  'What would my EMI be?',
]

export function Copilot() {
  const [text, setText] = useState('Can I afford ₹50k?')
  const [messages, setMessages] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pendingApproval, setPendingApproval] = useState<Message | null>(null)
  const [showSuggestions, setShowSuggestions] = useState(true)
  const inputRef = useRef<HTMLInputElement>(null)

  // Cmd+K to focus copilot input when on copilot page
  useKeyboardShortcut('k', () => {
    inputRef.current?.focus()
  })

  // Auto-send the default question on first load for demo
  useEffect(() => {
    if (messages.length === 0 && text === 'Can I afford ₹50k?') {
      const timer = setTimeout(() => {
        send()
      }, 800)
      return () => clearTimeout(timer)
    }
  }, [])

  async function send(e?: React.FormEvent) {
    e?.preventDefault()
    if (!text.trim()) return
    const question = text.trim()
    setMessages((v) => [...v, { from: 'you', text: question }])
    setText('')
    setBusy(true)
    setError('')
    setShowSuggestions(false)

    try {
      const res = await postJson<any>('/copilot/chat', {
        message: question,
        applicant_id: applicant,
      })
      await new Promise((r) => setTimeout(r, 450))

      const newMessage: Message = {
        from: 'agent',
        text: res.reply,
        tools: res.tools,
        analysis: res.analysis,
        approval: res.approval?.required
          ? {
              required: true,
              action: res.approval.action || 'Execute financial operation',
              amount: res.approval.amount,
              details: res.approval.details,
            }
          : undefined,
      }

      setMessages((v) => [...v, newMessage])

      // If approval is required, set it as pending
      if (res.approval?.required) {
        setPendingApproval(newMessage)
      }
    } catch (x) {
      setError(x instanceof Error ? x.message : 'Copilot unavailable')
    } finally {
      setBusy(false)
    }
  }

  function useSuggestion(q: string) {
    setText(q)
    setShowSuggestions(false)
  }

  async function approve() {
    if (!pendingApproval) return

    const sc = JSON.parse(sessionStorage.getItem('paypilot.score') || 'null')
    if (!sc) {
      setError('Run PayScore first. The server requires a successful score before payout.')
      return
    }

    try {
      const res = await postJson<any>('/disburse', {
        applicant_id: applicant,
        recipient_email: 'priya@example.test',
        approved_loan_amount_inr: (pendingApproval.approval as any)?.amount || 50000,
        note: 'Borrower explicitly approved sandbox demo payout',
      })
      sessionStorage.setItem('paypilot.payout_batch_id', res.payout_batch_id)

      setMessages((v) => [
        ...v,
        {
          from: 'agent',
          text: `✓ Sandbox payout created · batch ${res.payout_batch_id} · ${res.batch_status}`,
          approval: undefined,
          approved: true,
        },
      ])
      setPendingApproval(null)
      setError('')
    } catch (x) {
      setError(x instanceof Error ? x.message : 'Payout request failed')
    }
  }

  function decline() {
    setMessages((v) => [
      ...v,
      {
        from: 'agent',
        text: 'Action declined. No changes made to your account.',
        approval: undefined,
        approved: false,
      },
    ])
    setPendingApproval(null)
  }

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="AI copilot"
        title="Your financial copilot."
        detail="Ask about income, affordability, and your next step."
      />
      <Notice>
        Money-related actions always wait for your explicit approval. Demo actions are sandbox only.
      </Notice>

      <GlassCard className="mx-auto max-w-3xl">
        <div className="max-h-[52vh] min-h-72 space-y-4 overflow-y-auto p-4" aria-live="polite">
          {!messages.length && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="grid h-72 place-items-center text-center"
            >
              <div>
                <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-paypal/10 text-paypal">
                  <Icon name="spark" size={26} />
                </span>
                <p className="mt-4 font-semibold">Try "Can I afford ₹50k?"</p>
                <p className="mt-1 text-xs text-slate-500">I'll check your income and PayScore</p>
                {showSuggestions && (
                  <motion.div
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                    className="mt-6"
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-3">Quick questions</p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {SUGGESTED_QUESTIONS.map((q, i) => (
                        <motion.button
                          key={q}
                          initial={{ opacity: 0, scale: 0.9, y: 8 }}
                          animate={{ opacity: 1, scale: 1, y: 0 }}
                          transition={{ delay: 0.05 * i, type: 'spring', stiffness: 200, damping: 20 }}
                          onClick={() => useSuggestion(q)}
                          className="rounded-xl bg-slate-100 dark:bg-white/10 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-paypal/10 hover:text-paypal transition-colors"
                        >
                          {q}
                        </motion.button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}

          <AnimatePresence mode="popLayout">
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                transition={{ duration: 0.3 }}
                className={`flex gap-3 ${msg.from === 'you' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.from === 'agent' && (
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-paypal/10 text-paypal">
                    <Icon name="chat" size={16} />
                  </span>
                )}
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    msg.from === 'you'
                      ? 'bg-paypal text-white'
                      : msg.approved
                        ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                        : msg.approved === false
                          ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                          : 'bg-slate-100 dark:bg-white/10'
                  }`}
                >
                  <motion.p
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                    className="text-sm leading-relaxed"
                  >
                    {msg.text}
                  </motion.p>
                  {msg.analysis?.kind && (
                    <p className="mt-2 text-xs opacity-80">
                      Tool result: {msg.analysis.kind}
                      {msg.analysis.result?.status ? ` · ${msg.analysis.result.status}` : ''}
                    </p>
                  )}
                  {msg.approved && (
                    <Link to="/app/repay" className="mt-2 inline-flex text-xs font-semibold text-paypal underline underline-offset-4">
                      Track payout status
                    </Link>
                  )}

                  {/* Tool call chips */}
                  {msg.tools && msg.tools.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      className="mt-3 flex flex-wrap gap-2"
                    >
                      {msg.tools.map((tool, j) => (
                        <motion.span
                          key={j}
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={{ opacity: 1, scale: 1 }}
                          transition={{ delay: j * 0.1 }}
                          className="inline-flex items-center gap-1.5 rounded-full bg-paypal/10 px-2.5 py-1 text-[11px] font-semibold text-paypal"
                        >
                          <PulseDot />
                          {tool.label}
                        </motion.span>
                      ))}
                    </motion.div>
                  )}

                  {/* Approval card */}
                  {msg.approval?.required && pendingApproval === msg && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
                      className="mt-4 rounded-xl border border-amber-500/30 bg-amber-400/10 p-3"
                    >
                      <div className="flex items-start gap-2">
                        <Icon name="shield" className="mt-0.5 text-amber-600 dark:text-amber-300" />
                        <div className="flex-1">
                          <p className="text-xs font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300">
                            Approval required
                          </p>
                          <p className="mt-1 text-sm">{msg.approval.action}</p>
                          {msg.approval.amount && (
                            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
                              Amount: ₹{new Intl.NumberFormat('en-IN').format(msg.approval.amount)}
                            </p>
                          )}
                          {msg.approval.details && (
                            <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{msg.approval.details}</p>
                          )}
                          <div className="mt-3 flex gap-2">
                            <Button onClick={approve}>
                              Approve
                            </Button>
                            <Button variant="ghost" onClick={decline}>
                              Decline
                            </Button>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {busy && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex gap-3"
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-paypal/10 text-paypal">
                <Icon name="chat" size={16} />
              </span>
              <div className="flex items-center gap-2 rounded-2xl bg-slate-100 dark:bg-white/10 px-4 py-3">
                <div className="flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-paypal" style={{ animationDelay: '0ms' }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-paypal" style={{ animationDelay: '150ms' }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-paypal" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </motion.div>
          )}
        </div>

        <div className="border-t border-slate-200/60 dark:border-white/10 p-4">
          <form onSubmit={send} className="flex gap-2">
            <input
              ref={inputRef}
              aria-label="Ask the copilot"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Ask about income, affordability, or next steps"
              className={inputClass}
              disabled={busy}
            />
            <Button type="submit" disabled={busy || !text.trim()}>
              <Icon name="arrow" size={16} />
            </Button>
          </form>
          {showSuggestions && messages.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-3"
            >
              <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">Quick questions</p>
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUESTIONS.filter(q => q !== text).map((q, i) => (
                  <motion.button
                    key={q}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.05 * i }}
                    onClick={() => useSuggestion(q)}
                    className="rounded-xl bg-slate-100 dark:bg-white/10 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-paypal/10 hover:text-paypal transition-colors"
                  >
                    {q}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          )}
        </div>
      </GlassCard>

      {error && <Notice tone="error">{error}</Notice>}
    </div>
  )
}
