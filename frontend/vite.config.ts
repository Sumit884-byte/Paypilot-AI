import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'ag-grid',
              test: /node_modules[\\/]@ag-grid-community[\\/]/,
            },
          ],
        },
      },
    },
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
    },
  },
})
