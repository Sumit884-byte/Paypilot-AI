import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { MotionConfig } from 'framer-motion'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { AppShell } from './components/layout/AppShell'
import { Skeleton } from './components/ui/Skeleton'

const Landing = lazy(() => import('./pages/Landing').then((mod) => ({ default: mod.Landing })))
const AuthCallback = lazy(() => import('./pages/AuthCallback').then((mod) => ({ default: mod.AuthCallback })))
const Overview = lazy(() => import('./pages/Overview').then((mod) => ({ default: mod.Overview })))
const Income = lazy(() => import('./pages/Income').then((mod) => ({ default: mod.Income })))
const Score = lazy(() => import('./pages/Score').then((mod) => ({ default: mod.Score })))
const OfferGuard = lazy(() => import('./pages/OfferGuard').then((mod) => ({ default: mod.OfferGuard })))
const Copilot = lazy(() => import('./pages/Copilot').then((mod) => ({ default: mod.Copilot })))
const Repayment = lazy(() => import('./pages/Repayment').then((mod) => ({ default: mod.Repayment })))
const Cockpit = lazy(() => import('./pages/Cockpit').then((mod) => ({ default: mod.Cockpit })))

function LoadingScreen() {
  return <div className="mx-auto max-w-6xl space-y-5 p-6"><Skeleton className="h-8 w-48"/><Skeleton className="h-36"/><div className="grid gap-4 md:grid-cols-3">{[1, 2, 3].map((n) => <Skeleton key={n} className="h-32" />)}</div></div>
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Suspense fallback={<LoadingScreen />}>
              <Routes>
                <Route path="/" element={<Landing />} />
                <Route path="/auth/callback" element={<AuthCallback />} />
                <Route path="/app" element={<AppShell />}>
                  <Route index element={<Overview />} />
                  <Route path="income" element={<Income />} />
                  <Route path="score" element={<Score />} />
                  <Route path="offer-guard" element={<OfferGuard />} />
                  <Route path="copilot" element={<Copilot />} />
                  <Route path="repay" element={<Repayment />} />
                  <Route path="cockpit" element={<Cockpit />} />
                  <Route path="*" element={<Navigate to="/app" replace />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </MotionConfig>
  )
}
