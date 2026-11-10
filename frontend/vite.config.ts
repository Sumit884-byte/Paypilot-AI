import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  build: {
    // AG Grid's lazy-loaded chunk cannot be split further. The limit sits just
    // above it (kB) so any other oversized chunk still warns.
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    proxy: {
      '/paypal': 'http://127.0.0.1:8000',
      '/demo': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/score': 'http://127.0.0.1:8000',
      '/income-profile': 'http://127.0.0.1:8000',
      '/disburse': 'http://127.0.0.1:8000',
      '/repayment': 'http://127.0.0.1:8000',
      '/offer-guard': 'http://127.0.0.1:8000',
      '/copilot': 'http://127.0.0.1:8000',
      '/explain': 'http://127.0.0.1:8000',
      '/counterfactuals': 'http://127.0.0.1:8000',
      '/affordability': 'http://127.0.0.1:8000',
      '/revenue-volatility': 'http://127.0.0.1:8000',
      '/model-card': 'http://127.0.0.1:8000',
      '/income-passport': 'http://127.0.0.1:8000',
      // Public React page is /verify/... — do not proxy that path to the API.
      '/api': 'http://127.0.0.1:8000',
      '/negotiate': 'http://127.0.0.1:8000',
    },
  },
})
