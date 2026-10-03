// Onboarding answers. Prefilled with the Harbor Point demo practice so a demo can click straight through.
// Nothing here is sent to the backend.

export type TeamRole = 'partner' | 'ops' | 'lpl_bookkeeper';
export type Member = { id: string; name: string; email: string; role: TeamRole };
export type RevenueType = 'advisory' | 'commissions' | 'trails' | 'planning';
export type Answers = {
  practiceName: string; yourName: string; email: string;
  aum: number; clients: number; revenue: RevenueType[];
  team: Member[];
  rules: Record<string, boolean>;
  payoutsConnected: boolean; files: string[];
};

export const STEPS = [
  { key: 'practice', name: 'Your practice' },
  { key: 'business', name: 'The business' },
  { key: 'team', name: 'Team & roles' },
  { key: 'rules', name: 'Approval rules' },
  { key: 'documents', name: 'Documents' },
] as const;

export const ROLE_INFO: Record<TeamRole, { label: string; blurb: string }> = {
  partner: { label: 'Partner', blurb: 'Approves large bills' },
  ops: { label: 'Operations', blurb: 'Uploads and prepares bills' },
  lpl_bookkeeper: { label: 'LPL bookkeeper', blurb: 'Reviews the books' },
};

export const REVENUE_TYPES: { key: RevenueType; label: string }[] = [
  { key: 'advisory', label: 'Advisory fees' },
  { key: 'commissions', label: 'Commissions' },
  { key: 'trails', label: '12b-1 trails' },
  { key: 'planning', label: 'Planning fees' },
];

export const STARTER_RULES = [
  { id: 'threshold', title: 'Bills over $1,000 need a partner', detail: 'Smaller bills from known vendors are approved automatically.' },
  { id: 'vendor_docs', title: 'Hold new vendors until W-9 + void check', detail: 'Released on its own once both documents arrive.' },
  { id: 'received', title: 'Confirm goods received before paying', detail: 'For purchase orders and equipment.' },
  { id: 'duplicate', title: 'Block duplicate invoices', detail: 'Same vendor, number and amount is stopped.' },
] as const;

export const SETUP_TASKS = ['Creating your ledger', 'Loading an advisor chart of accounts', 'Turning on approval rules', 'Inviting your team'];

export const DEFAULT_ANSWERS: Answers = {
  practiceName: 'Harbor Point Wealth', yourName: 'Maya Chen', email: 'maya@harborpoint.example',
  aum: 250, clients: 180, revenue: ['advisory', 'commissions', 'trails'],
  team: [
    { id: 'raj', name: 'Raj Patel', email: 'raj@harborpoint.example', role: 'partner' },
    { id: 'dev', name: 'Dev Shah', email: 'dev@harborpoint.example', role: 'ops' },
  ],
  rules: { threshold: true, vendor_docs: true, received: true, duplicate: true },
  payoutsConnected: false, files: [],
};

export const isEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.trim());

// Returns why the step can't continue yet, or '' when it can.
export function stepProblem(step: number, a: Answers): string {
  if (step === 0) {
    if (!a.practiceName.trim()) return 'Add your practice name.';
    if (!a.yourName.trim()) return 'Add your name.';
    if (!isEmail(a.email)) return 'Enter a valid work email.';
  }
  if (step === 1 && !a.revenue.length) return 'Pick at least one way you are paid.';
  if (step === 2) {
    const bad = a.team.find(m => !m.name.trim() || !isEmail(m.email));
    if (bad) return 'Each teammate needs a name and a valid email.';
  }
  return '';
}

export const STORAGE_KEY = 'otter-onboarding';
export const LOGIN_PREFILL_KEY = 'otter-login-email';
