import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
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
    },
  },
})
