import { Fragment } from 'react'
import { Navigate, useOutlet } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useActivePersona } from '../../lib/personas'
import { PageTransition } from './PageTransition'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppShell() {
  const { isAuthed } = useAuth()
  const persona = useActivePersona()
  // Captured per route so the exiting page keeps rendering itself, not the next route
  const outlet = useOutlet()

  if (!isAuthed) return <Navigate to="/" replace />

  return (
    <div className="flex min-h-svh flex-col bg-[rgb(var(--bg))]">
      <Topbar onMenu={() => undefined} />
      <Sidebar />
      <main className="mx-auto w-full max-w-[1600px] min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <PageTransition>
          {/* Keyed by persona so a switch remounts the page with the new persona's data */}
          <Fragment key={persona.key}>{outlet}</Fragment>
        </PageTransition>
      </main>
      <footer className="flex flex-wrap justify-between gap-2 border-t border-[rgb(var(--line))] px-4 py-3 text-[10px] text-slate-500 sm:px-6 lg:px-10">
        <span>SANDBOX ONLY · Synthetic estimates. Not a lending decision. No real money movement.</span>
        <span>{persona.firstName} / India · INR</span>
      </footer>
    </div>
  )
}
