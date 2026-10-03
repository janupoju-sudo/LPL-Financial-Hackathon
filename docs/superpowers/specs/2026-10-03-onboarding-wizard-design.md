# Otter landing page, onboarding wizard and rename

Date: 2026-10-03 · Owner: C (Jay) · Status: approved in chat

## Goal
A demo showpiece for the pitch: a visitor lands on a marketing page, walks through a polished sign-up
wizard for a new advisor practice, and ends at sign-in with Maya's email filled in. No real accounts are
created; Cognito self-signup stays off (#16). The product is renamed from Ledgerline to **Otter**.

## Routes (signed out)
| Path | Shows |
|---|---|
| `/` | Landing page |
| `/signup` | 5-step onboarding wizard |
| `/login` (and any app path) | Amplify sign-in; email prefilled after the wizard |

Signed-in users never see the landing page or wizard; `/login`, `/signup` and `/welcome` redirect to `/`.
Mock / local mode has no sign-in: landing at `/welcome`, wizard at `/signup`, finishing opens the app.

## Wizard steps
1. Your practice: practice name, your name, email (prefilled Harbor Point Wealth / Maya Chen)
2. About the business: AUM slider, client count, revenue types (advisory fees, commissions, trails)
3. Team and roles: Raj (partner, approves large bills), Dev (ops); add/remove people, pick roles
4. Approval rules: starter rules as toggles (partner approval over $1,000, hold new vendors for W-9 +
   void check, received-before-pay, duplicate invoice block)
5. Documents: illustrative drop zone and "Connect LPL payout statements", then a ~4s "Setting up your
   books" checklist, then "You're ready" with **Open my workspace**

Progress bar with step names, Back / Continue, Enter to continue, light validation (practice name and a
valid email required), Skip and "Already have an account? Sign in" on every step. Answers live in React
state mirrored to sessionStorage (try/catch); nothing is sent to the backend. A footer note says
"Demo onboarding".

## Components
- `components/landing.tsx` — hero, animated invoice → bill → approved preview, 4 feature cards, trust strip
- `components/onboarding/wizard.tsx` — shell, progress, step transitions, persistence
- `components/onboarding/steps.tsx` — the five steps and the setup/ready screens
- `components/onboarding/data.ts` — prefill values, starter rules, step list
- `components/motion.ts` — shared spring, variants and stagger so every animation feels the same
- `components/brand.tsx` — Otter logo / mark (light and dark)
- `workspace.tsx` — only the signed-out routing and brand changes

## Animation
`motion` (Framer Motion's current package, `motion/react`). One spring; slide + fade between steps
(direction-aware), staggered reveals, layout-animated progress bar, checkmark path draw, checklist ticks.
`MotionConfig reducedMotion="user"`. Colors from the existing glass tokens, so dark mode works.

## Rename
User-facing text only: page title, sidebar brand, landing/wizard, favicon (`app/icon.png`) and logo
(`public/otter-logo.png`, `public/otter-mark.png`, made transparent from the supplied PNG). AWS
resource names (`ledgerline-dev` stack, table, buckets) and internal keys (`ledgerline-theme`) stay, so
the live stack is untouched.

## Testing
`npm run typecheck`, `npm run build`, `npm test`; click through landing → wizard (all steps, Back,
refresh mid-wizard) → sign-in in the browser at desktop and phone width, light and dark.
