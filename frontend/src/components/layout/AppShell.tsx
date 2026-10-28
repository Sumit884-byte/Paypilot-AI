import { useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { AmbientBackground } from '../ui/AmbientBackground'
import { useAuth } from '../../context/AuthContext'
import { PageTransition } from './PageTransition'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppShell() {
  const { isAuthed } = useAuth()
  const [open, setOpen] = useState(false)

  if (!isAuthed) return <Navigate to="/" replace />

  return (
    <div className="relative min-h-svh bg-[rgb(var(--bg))]">
      <AmbientBackground />

      <div className="relative flex min-h-svh">
        <div className="hidden w-60 shrink-0 border-r border-white/[.07] bg-[#0b1422] lg:block">
          <Sidebar />
        </div>

        <AnimatePresence>
          {open && (
            <motion.div
              className="fixed inset-0 z-40 lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <button
                type="button"
                className="absolute inset-0 bg-navy-950/55"
                aria-label="Close navigation"
                onClick={() => setOpen(false)}
              />
              <motion.div
                initial={{ x: -240 }}
                animate={{ x: 0 }}
                exit={{ x: -240 }}
                transition={{ type: 'spring', stiffness: 320, damping: 32 }}
                className="relative h-full w-60 bg-[#0b1422] shadow-glass-lg"
              >
                <Sidebar onNavigate={() => setOpen(false)} />
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onMenu={() => setOpen(true)} />
          <main className="min-w-0 flex-1 p-4 sm:p-5 lg:px-6 lg:py-5">
            <PageTransition>
              <Outlet />
            </PageTransition>
          </main>
        </div>
      </div>
    </div>
  )
}
