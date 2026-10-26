/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#070B14',
          900: '#0B1220',
          800: '#111A2E',
          700: '#1A2744',
          600: '#243556',
        },
        paypal: {
          DEFAULT: '#0070BA',
          dark: '#003087',
          light: '#009CDE',
          gold: '#FFC439',
        },
        amber: {
          glow: '#F5B942',
        },
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
        display: ['"Plus Jakarta Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        glass: '0 8px 32px rgba(7, 11, 20, 0.28), inset 0 1px 0 rgba(255,255,255,0.08)',
        'glass-lg': '0 24px 80px rgba(7, 11, 20, 0.45), inset 0 1px 0 rgba(255,255,255,0.1)',
        glow: '0 0 40px rgba(0, 112, 186, 0.25)',
        'glow-gold': '0 0 36px rgba(245, 185, 66, 0.28)',
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      backgroundImage: {
        'mesh-dark':
          'radial-gradient(ellipse 80% 60% at 20% 10%, rgba(0,112,186,0.22), transparent 50%), radial-gradient(ellipse 60% 50% at 90% 20%, rgba(245,185,66,0.12), transparent 45%), radial-gradient(ellipse 50% 40% at 50% 90%, rgba(0,156,222,0.12), transparent 50%)',
        'mesh-light':
          'radial-gradient(ellipse 80% 60% at 20% 10%, rgba(0,112,186,0.12), transparent 50%), radial-gradient(ellipse 60% 50% at 90% 20%, rgba(245,185,66,0.16), transparent 45%), radial-gradient(ellipse 50% 40% at 50% 90%, rgba(0,48,135,0.06), transparent 50%)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'gradient-shift': {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '0.45' },
          '50%': { opacity: '0.85' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s ease-in-out infinite',
        float: 'float 6s ease-in-out infinite',
        'gradient-shift': 'gradient-shift 8s ease infinite',
        pulseGlow: 'pulseGlow 4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
