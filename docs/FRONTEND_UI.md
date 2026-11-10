# Paypilot AI Frontend - UI Documentation

## Overview

Paypilot AI is a premium fintech application for the PayPal AI Hackathon. The frontend is built with React 18, TypeScript, Vite, Tailwind CSS, and Framer Motion, featuring a dark navy/charcoal design system with PayPal blue (#0070BA) and warm gold/amber accents.

## Design System

### Color Palette
- **Navy Base**: Dark navy/charcoal backgrounds (`#070B14`, `#0B1220`)
- **PayPal Blue**: Primary accent (`#0070BA`, `#009CDE`, `#003087`)
- **Gold Accent**: Warm gold/amber for highlights (`#F5B942`, `#FFC439`)
- **Risk Colors**: Green (low), Amber (moderate), Orange (elevated), Rose (high)

### Typography
- **Font Family**: Plus Jakarta Sans (primary), Inter (fallback)
- **Display Font**: Plus Jakarta Sans for headings
- **Weights**: Regular (400), Medium (500), Semibold (600), Bold (700)

### Components
- **GlassCard**: Glassmorphism cards with backdrop blur and subtle borders
- **Button**: Primary action buttons with hover lift animation
- **Skeleton**: Loading states with shimmer effect
- **ProgressRing**: Circular progress indicators with animated stroke
- **MetricCard**: Stat cards with count-up animation
- **Notice**: Informational, warning, and error banners

### Animations
- **Page Transitions**: Fade + slide with stagger children
- **Hover Effects**: Scale and lift on interactive elements
- **Parallax**: 3D mouse-move parallax on landing page cards
- **Signature Moments**: Confetti burst, success checkmark, live score pulse

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies API calls to `http://127.0.0.1:8000`.

## Demo Mode Walkthrough

The demo mode provides a complete 3-minute flow using the Priya persona. Here's the step-by-step walkthrough:

### Step 1: Landing Page
1. Open the application at `http://localhost:5173`
2. Click **"Tour the cockpit"** to enter demo mode (no PayPal credentials needed)
3. Observe the animated landing page with:
   - Floating dashboard cards with 3D parallax on mouse move
   - Animated gradient headline
   - Official PayPal login button (configured for sandbox)
   - Sandbox disclaimer badge

### Step 2: Overview Dashboard
1. After entering demo mode, you'll see the Overview page
2. Review the animated stat cards:
   - 12-month income with count-up animation
   - Distinct client count
   - Refund and dispute rates
   - Longest payment gap
3. Click **"Run PayScore"** to navigate to the scoring page

### Step 3: Income Profile
1. Navigate to **Income** from the sidebar
2. View the 12-month income area chart (Recharts) that animates on load
3. Review payment rhythm indicators:
   - Monthly direction (increasing/decreasing/stable)
   - Longest income gap
   - Client retention metrics
4. Scroll down to see the **AG Grid transaction feed**:
   - Custom cell renderers for amount, type, and status
   - PayScore theming (PayPal blue headers)
   - Sortable and filterable columns
   - Color-coded transaction types

### Step 4: Explainable Score
1. Navigate to **PayScore** from the sidebar
2. Click **"Run PayScore"** to generate a score
3. Observe the animated circular gauge (300-850 scale) with needle sweep
4. Review the risk band badge (color-coded: green/amber/orange/rose)
5. See the top-3 reason cards with staggered animation
6. Read the "to move up" action line with actionable advice
7. Check disbursement eligibility status

### Step 5: Offer Guard
1. Navigate to **Offer guard** from the sidebar
2. Enter sample loan offer details:
   - Lender: "Example NBFC"
   - Advertised APR: 18%
   - Processing fee: 4%
   - Principal: ₹50,000
   - Term: 12 months
3. Click **"Analyze offer"**
4. Watch the red-flag highlight (if real APR > advertised)
5. Review the KFS checklist with item-by-item animation
6. Check the RBI directory match result with CRL verification

### Step 6: AI Copilot
1. Navigate to **AI copilot** from the sidebar
2. Type: **"Can I afford ₹50k?"**
3. Watch the typing indicator and tool-call chips animation
4. Review the agent's response with affordability analysis
5. When money-related action is required, the approval card appears:
   - Action description
   - Amount details
   - Additional context
   - Approve/Decline buttons
6. Click **"Approve"** to proceed with the sandbox payout
7. Observe the success message

### Step 7: Repayment
1. Navigate to **Repayment** from the sidebar
2. Choose a repayment mode:
   - **Fixed EMI**: Create a subscription with monthly installments
   - **Revenue share**: Configure percentage-based repayment
   - **One-off**: Single payment via PayPal JS SDK
3. For Fixed EMI:
   - Enter EMI amount (₹5,000)
   - Enter number of EMIs (12)
   - Click **"Create subscription"**
   - View the repayment schedule timeline
4. For One-off:
   - Enter amount (₹5,000)
   - Click **"Create order"**
   - Pay with the PayPal JS SDK smart button
   - Observe the confetti burst and success animation
5. Watch for **"Score updated live"** pulse when webhook updates the score

### Step 8: AG Studio Cockpit
1. Navigate to **AG Studio** from the sidebar
2. See the default widgets:
   - Advertised vs real APR
   - Score drivers
   - Repayment progress
3. Add custom widgets using natural language:
   - Type: "show my income by client"
   - Click **"Add widget"**
   - Watch the spring animation as the widget appears
4. Remove widgets by clicking the menu icon
5. Click widget links to navigate to detailed pages

## Key Features

### Landing Page
- ✅ Animated gradient headline with continuous color shift
- ✅ 3D parallax effect on floating cards (mouse move)
- ✅ Animated wordmark with letter-by-letter entrance
- ✅ Official PayPal login button (sandbox)
- ✅ Sandbox disclaimer badge
- ✅ Responsive design

### Income Profile
- ✅ Animated stat cards with count-up animation
- ✅ Recharts area chart with draw animation
- ✅ AG Grid with PayScore theming (sponsor prize)
- ✅ Custom cell renderers (amount, type, status)
- ✅ Payment rhythm indicators
- ✅ 12-month transaction feed

### Explainable Score
- ✅ Animated circular gauge (300-850)
- ✅ Needle sweep animation
- ✅ Risk band badge with color coding
- ✅ Top-3 reason cards with staggered animation
- ✅ "to move up" action line
- ✅ Disbursement eligibility status

### Offer Guard
- ✅ Red-flag highlight for hidden costs
- ✅ KFS checklist with item-by-item animation
- ✅ RBI directory match result
- ✅ Advertised vs real APR comparison
- ✅ Analyzing state with loading spinner

### AI Copilot
- ✅ Polished chat panel with message bubbles
- ✅ Typing indicator (bouncing dots)
- ✅ Streaming-style message reveal
- ✅ Tool-call chips animation
- ✅ Explicit approval for money-related actions
- ✅ Approval card with Approve/Decline buttons

### Repayment
- ✅ Toggle between Fixed EMI / Revenue-share / One-off
- ✅ EMI schedule timeline
- ✅ PayPal JS SDK v6 smart button
- ✅ Live repayment-progress ring
- ✅ Confetti burst on payment success
- ✅ Glowing success checkmark animation
- ✅ Animated "score updating live" pulse

### AG Studio Cockpit
- ✅ Custom widgets with Paypilot AI theming
- ✅ Natural-language question bar
- ✅ Spring animation for new widgets
- ✅ Widget removal functionality
- ✅ Gradient backgrounds per widget type

## Accessibility

- ✅ Keyboard navigation with visible focus rings
- ✅ Reduced-motion support (`prefers-reduced-motion`)
- ✅ ARIA labels on interactive elements
- ✅ Semantic HTML structure
- ✅ Color contrast compliance (WCAG AA)

## Performance

- ✅ Lazy-loaded routes (React.lazy)
- ✅ Code splitting by route
- ✅ Optimized bundle size
- ✅ Image optimization (SVG icons)
- ✅ Animation performance (GPU-accelerated transforms)
- ✅ Lighthouse-friendly (target: 90+ performance)

## Environment Variables

```bash
# API proxy (empty for local development)
VITE_PAYSCORE_API_URL=

# Optional: override API base URL for production
VITE_PAYSCORE_API_URL=https://your-api.example.com
```

## Tech Stack

- **React 18**: UI framework
- **TypeScript**: Type safety
- **Vite**: Build tool and dev server
- **Tailwind CSS**: Utility-first styling
- **Framer Motion**: Animation library
- **React Router v7**: Client-side routing
- **AG Grid Community**: Data grid (sponsor prize)
- **Recharts**: Charting library
- **clsx & tailwind-merge**: Conditional class names

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Deployment

### Build for Production
```bash
npm run build
```

### Preview Production Build
```bash
npm run preview
```

### Render Deployment
The `render.yaml` in the parent directory configures deployment for the API. The frontend can be deployed separately to Vercel, Netlify, or any static hosting service.

## Screenshots

*(Note: Screenshots should be added here after capturing them)*

### Landing Page
- [Landing page with floating cards]
- [Parallax effect demonstration]

### Income Profile
- [Animated stat cards]
- [Recharts area chart]
- [AG Grid transaction feed]

### Explainable Score
- [Circular gauge with needle]
- [Reason cards with animation]

### Offer Guard
- [Red-flag highlight]
- [KFS checklist]
- [RBI directory match]

### AI Copilot
- [Chat panel with approval card]
- [Tool-call chips]

### Repayment
- [PayPal JS SDK button]
- [Confetti burst animation]
- [Live score pulse]

### AG Studio Cockpit
- [Widget grid with gradients]
- [Natural-language input]

## Demo Video Script

The 3-minute demo video should follow this flow:

1. **0:00-0:30**: Landing page - highlight parallax and animations
2. **0:30-0:45**: Enter demo mode, show overview
3. **0:45-1:00**: Income profile with AG Grid
4. **1:00-1:15**: Explainable score with gauge animation
5. **1:15-1:30**: Offer guard with red-flag detection
6. **1:30-1:45**: AI copilot with approval flow
7. **1:45-2:00**: Repayment with PayPal button
8. **2:00-2:15**: Confetti celebration
9. **2:15-2:30**: AG Studio cockpit with widgets
10. **2:30-3:00**: Summary and closing

## Troubleshooting

### API Connection Issues
- Ensure the FastAPI backend is running on port 8000
- Check CORS configuration in `.env`
- Verify `VITE_PAYSCORE_API_URL` if using remote API

### PayPal Sandbox Issues
- Ensure sandbox credentials are set in backend `.env`
- Check `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`
- Verify sandbox mode is enabled

### AG Grid Not Rendering
- Ensure `ag-grid-community` is installed
- Check that CSS imports are present
- Verify column definitions are valid

### Performance Issues
- Check bundle size with `npm run build`
- Ensure lazy loading is working
- Disable heavy animations in production if needed

## Contributing

When adding new features:
1. Follow the existing design system
2. Use TypeScript for type safety
3. Add proper accessibility attributes
4. Include reduced-motion support
5. Test with keyboard navigation
6. Update this README with new features

## License

This project is part of the PayPal AI Hackathon. All code is proprietary and confidential.
