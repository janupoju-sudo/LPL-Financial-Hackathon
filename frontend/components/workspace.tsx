'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Amplify } from 'aws-amplify';
import { Authenticator, useAuthenticator } from '@aws-amplify/ui-react';
import { MotionConfig } from 'motion/react';
import '@aws-amplify/ui-react/styles.css';
import { Area, AreaChart, Bar, BarChart, Cell, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowDown, ArrowDownToLine, ArrowRight, ArrowUp, ArrowUpRight, Check, CircleHelp, CreditCard, FileText, FolderOpen, Home, LoaderCircle, LogOut, Moon, Plus, Search, Send, ShieldCheck, SlidersHorizontal, Sparkles, Trash2, UploadCloud, Wallet, X } from 'lucide-react';
import { api, subscribe, USE_MOCKS, USE_LOCAL_API } from '@/lib/api';
import type { Answer, Bill, BillApprovalChanges, BillDetail, BillReview, CardTransaction, Document, Financials, Reconciliation, Role, Rule, RuleCondition, Vendor } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { FinancialStatement } from './financial-statements';
import { Revenue } from './revenue-view';
import { percent } from '@/lib/format';
import { ProfileSettings } from './profile-settings';
import { GoogleDriveImport } from './google-drive-import';
import { canApproveBill, canImportTransactions, canManageRules, canReviewDocuments, canUploadDocuments } from '@/lib/permissions';
import { Landing } from './landing';
import { OnboardingWizard } from './onboarding/wizard';
import { LOGIN_PREFILL_KEY } from './onboarding/data';
import { OtterLogo, OtterMark } from './brand';

const money = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);
function Amount({ value }: { value: number }) { const [whole, frac] = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value).split('.'); return <>{whole}<small>.{frac}</small></>; }
const cents = (n: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
const label = (s?: string | null) => s ? s.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) : '';
// Four places. Money out and Documents each hold a few pages, shown as tabs inside the place.
const nav = [
  { name: 'Home', path: '/', icon: Home, match: ['/'] },
  { name: 'Money in', path: '/revenue', icon: ArrowDown, match: ['/revenue'] },
  { name: 'Money out', path: '/bills', icon: ArrowUp, match: ['/bills', '/transactions', '/rules'] },
  { name: 'Documents', path: '/documents', icon: FileText, match: ['/inbox', '/library', '/documents'] },
];
const SUBNAV = [
  [{ name: 'Bills & approvals', path: '/bills', icon: Wallet }, { name: 'Card spend', path: '/transactions', icon: CreditCard }, { name: 'Rules', path: '/rules', icon: SlidersHorizontal }],
];
const ROUTES = ['/', '/revenue', '/bills', '/transactions', '/rules', '/documents', '/inbox', '/library', '/ask'];
const ASK_SUGGESTIONS = ['Why did my margin drop in Q3?', 'Which payouts need follow-up?', 'What are my largest expenses?'];
const isActive = (match: string[], path: string) => match.some(m => m === '/' ? path === '/' : path === m || path.startsWith(`${m}/`));
const DEMO_PEOPLE: Record<string, string> = { maya: 'Maya Chen', raj: 'Raj', dev: 'Dev', priya: 'Priya' };
const displayName = (email: string) => { const local = email.split('@')[0].toLowerCase(); return DEMO_PEOPLE[local] ?? local.replace(/[._-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); };
const authConfigured = Boolean(process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID && process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID);
if (authConfigured) Amplify.configure({ Auth: { Cognito: { userPoolId: process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID!, userPoolClientId: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID! } } });

export function Workspace() {
  if (USE_MOCKS || USE_LOCAL_API) return <MotionConfig reducedMotion="user"><MockGate /></MotionConfig>;
  if (!authConfigured) return <main className="login"><OtterMark size={40} /><h1>Connect your practice</h1><p>Set the Cognito user pool and client ID in frontend/.env.local to enable secure sign-in.</p></main>;
  return <MotionConfig reducedMotion="user"><Authenticator.Provider><AuthGate /></Authenticator.Provider></MotionConfig>;
}

// Signed-out pages. The landing page and wizard are a demo of onboarding: no account is created
// (self-signup is off), the wizard ends at sign-in with the email filled in.
const ENTRY_PATHS = ['/login', '/signup', '/welcome'];

// Mock/local mode has no sign-in, so the landing page lives at /welcome and the app stays at /.
function MockGate() {
  const pathname = usePathname(); const router = useRouter();
  if (pathname === '/welcome') return <Landing onStart={() => router.push('/signup')} onSignIn={() => router.push('/')} />;
  if (pathname === '/signup') return <OnboardingWizard live={false} onFinish={() => router.push('/')} onSignIn={() => router.push('/')} onExit={() => router.push('/welcome')} />;
  return <App />;
}

function AuthGate() {
  const { authStatus, signOut } = useAuthenticator(ctx => [ctx.authStatus]);
  const pathname = usePathname(); const router = useRouter();
  const signedIn = authStatus === 'authenticated';
  useEffect(() => { if (signedIn && ENTRY_PATHS.includes(pathname)) router.replace('/'); }, [signedIn, pathname, router]);
  if (authStatus === 'configuring' || (signedIn && ENTRY_PATHS.includes(pathname))) return <div className="gate-loading" />;
  if (signedIn) return <App signOut={signOut} />;
  if (pathname === '/') return <Landing onStart={() => router.push('/signup')} onSignIn={() => router.push('/login')} />;
  if (pathname === '/signup') return <OnboardingWizard live onFinish={email => { try { sessionStorage.setItem(LOGIN_PREFILL_KEY, email); } catch { /* prefill is optional */ } router.push('/login'); }} onSignIn={() => router.push('/login')} onExit={() => router.push('/')} />;
  return <SignIn onHome={() => router.push('/')} onSignup={() => router.push('/signup')} />;
}

const SIGN_IN_FIELDS = { signIn: { username: { label: 'Email', placeholder: 'you@practice.com' } } };

function SignIn({ onHome, onSignup }: { onHome: () => void; onSignup: () => void }) {
  // Amplify's form has no prefill option, so set the email field the way typing would.
  useEffect(() => {
    let email = ''; try { email = sessionStorage.getItem(LOGIN_PREFILL_KEY) ?? ''; } catch { /* no prefill */ }
    if (!email) return;
    let tries = 0;
    const timer = setInterval(() => {
      const input = document.querySelector<HTMLInputElement>('[data-amplify-authenticator] input[name="username"]');
      if (input || ++tries > 40) clearInterval(timer);
      if (!input || input.value) return;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, email);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector<HTMLInputElement>('[data-amplify-authenticator] input[name="password"]')?.focus();
    }, 50);
    return () => clearInterval(timer);
  }, []);
  const components = useMemo(() => ({
    Header: () => <div className="signin-head"><button type="button" onClick={onHome} aria-label="Back to the Otter home page"><OtterLogo height={30} /></button></div>,
    Footer: () => <p className="signin-foot">New to Otter? <button type="button" onClick={onSignup}>Set up your practice</button></p>,
  }), [onHome, onSignup]);
  return <Authenticator hideSignUp components={components} formFields={SIGN_IN_FIELDS} />;
}

function App({ signOut }: { signOut?: () => void }) {
  const pathname = usePathname(); const path = ['/inbox', '/library'].includes(pathname) ? '/documents' : pathname; const router = useRouter();
  const [role, setRole] = useState<Role>(USE_MOCKS || USE_LOCAL_API ? 'owner' : 'lpl_bookkeeper'); const [roleLoaded, setRoleLoaded] = useState(USE_MOCKS || USE_LOCAL_API); const [userName, setUserName] = useState('Maya Chen'); const [userId, setUserId] = useState('');
  const [documents, setDocuments] = useState<Document[]>([]); const [bills, setBills] = useState<Bill[]>([]); const [vendors, setVendors] = useState<Vendor[]>([]); const [rules, setRules] = useState<Rule[]>([]);
  const [financials, setFinancials] = useState<Financials>(); const [revenue, setRevenue] = useState<Reconciliation>();
  const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [toast, setToast] = useState('');
  const [period, setPeriod] = useState('2026-Q3'); const [busy, setBusy] = useState(''); const [selected, setSelected] = useState<Document>(); const [billDetail, setBillDetail] = useState<BillDetail>();
  const [palette, setPalette] = useState(false); const [askOpen, setAskOpen] = useState(false); const [askRequest, setAskRequest] = useState<{ q: string; n: number }>();
  const refresh = useCallback(async () => {
    setError('');
    const results = await Promise.allSettled([api.documents(), api.bills(), api.vendors(), api.rules(), api.financials(period), api.reconciliation('2026-09')]);
    const setters = [setDocuments, setBills, setVendors, setRules, setFinancials, setRevenue];
    results.forEach((result, index) => { if (result.status === 'fulfilled') (setters[index] as (value: unknown) => void)(result.value); else setError(result.reason instanceof Error ? result.reason.message : 'Could not load practice data.'); });
    setLoading(false);
  }, [period]);
  useEffect(() => { void refresh(); return subscribe(() => { void refresh(); }); }, [refresh]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 5000); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    if (!selected) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setSelected(undefined); return; }
      if (event.key !== 'Tab') return;
      const elements = Array.from(document.querySelectorAll<HTMLElement>('.document-modal button:not(:disabled), .document-modal a[href], .document-modal iframe'));
      const first = elements[0]; const last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, [selected]);
  useEffect(() => { if (USE_MOCKS || USE_LOCAL_API) return; import('aws-amplify/auth').then(async ({ fetchAuthSession }) => { const payload = (await fetchAuthSession()).tokens?.idToken?.payload; const groups = payload?.['cognito:groups']; if (typeof payload?.email === 'string') setUserName(displayName(payload.email)); if (typeof payload?.sub === 'string') setUserId(payload.sub); if (Array.isArray(groups)) { const actual = ['owner', 'partner', 'ops', 'lpl_bookkeeper'].find(group => groups.includes(group)); if (actual) setRole(actual as Role); } setRoleLoaded(true); }).catch(() => setRoleLoaded(true)); }, []);
  useEffect(() => { if (!billDetail) return; const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setBillDetail(undefined); }; document.addEventListener('keydown', onKey); return () => document.removeEventListener('keydown', onKey); }, [billDetail]);
  const openBill = async (id: string) => { setBusy(id); try { setBillDetail(await api.bill(id)); } catch (e) { setToast(message(e)); } finally { setBusy(''); } };
  const openDoc = async (id: string) => { setBusy(id); try { setSelected(await api.document(id)); } catch (e) { setToast(message(e)); } finally { setBusy(''); } };
  const decide = async (bill: Bill, decision: 'approve' | 'reject', comment = '', changes?: BillApprovalChanges) => {
    setBusy(bill.id);
    try {
      await api.decision(bill.id, decision, comment.trim() || `${label(decision)}d by ${label(role)}`, role, changes);
      // The approval workflow posts to the ledger and schedules payment in a second or two; wait for it.
      let status = 'processing';
      for (let i = 0; i < 8 && status === 'processing'; i++) { await new Promise(r => setTimeout(r, 1200)); status = (await api.bill(bill.id)).status; }
      setBillDetail(undefined);
      setToast(decision === 'reject' ? `Rejected ${bill.vendor} · ${money(bill.amount)}.` : status === 'scheduled' ? `Approved ${bill.vendor} · ${money(bill.amount)}. Posted to the ledger and payment scheduled (mock).` : `Approved ${bill.vendor}. Still finishing up; it will show as scheduled shortly.`);
      await refresh();
    } catch (e) { setToast(decisionError(e)); } finally { setBusy(''); }
  };
  const exportPackage = async () => { setBusy('export'); try { const { downloadUrl, documents: exportedDocs, ledgerLines, missing } = await api.export(period); const a = document.createElement('a'); a.href = downloadUrl; a.download = `ledgerline-${period}.zip`; a.click(); if (downloadUrl.startsWith('blob:')) setTimeout(() => URL.revokeObjectURL(downloadUrl), 10000); setToast(`Export ready: ${exportedDocs} documents, ${ledgerLines} ledger lines.${missing.length ? ` Missing: ${missing.join(', ')}` : ''}`); } catch (e) { setToast(message(e)); } finally { setBusy(''); } };
  const pending = bills.filter(b => b.status === 'pending_approval' && canApprove(b, role, userId));
  const canUpload = roleLoaded && canUploadDocuments(role);
  const canReview = roleLoaded && canReviewDocuments(role);
  const canImport = roleLoaded && canImportTransactions(role);
  const attention = bills.filter(b => (b.status === 'pending_review' && canReview) || (b.status === 'pending_approval' && canApprove(b, role, userId))).length;
  // A document follows its bill once the bill moves past review (approved, scheduled, on hold, rejected).
  const docs = useMemo(() => withBillStatus(documents, bills), [documents, bills]);
  const docsWaiting = docs.filter(d => NEEDS_ATTENTION.includes(d.status)).length;
  const counts: Record<string, number> = { '/revenue': revenue && canUploadDocuments(role) ? (statementMissing(revenue) ? 1 : revenue.flags.length) : 0, '/bills': attention, '/documents': docsWaiting };
  const subnav = SUBNAV.map(group => group.filter(item => item.path !== '/rules' || (roleLoaded && canManageRules(role)))).find(group => group.some(item => item.path === path));
  const openAsk = useCallback((q?: string) => { setAskOpen(true); if (q) setAskRequest(r => ({ q, n: (r?.n ?? 0) + 1 })); }, []);
  useEffect(() => { if (path === '/ask') { openAsk(); router.replace('/'); } }, [path, openAsk, router]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(open => !open); }
      else if (e.key === 'Escape' && askOpen && !palette && !selected && !billDetail) setAskOpen(false);
    };
    document.addEventListener('keydown', onKey); return () => document.removeEventListener('keydown', onKey);
  }, [askOpen, palette, selected, billDetail]);
  const commands = useMemo<Command[]>(() => [
    ...(canUpload ? [{ group: 'Actions', label: 'Upload a document', icon: UploadCloud, run: () => router.push('/documents?upload=1') }] : []),
    { group: 'Actions', label: `Export the ${period} package`, icon: ArrowDownToLine, run: () => void exportPackage() },
    { group: 'Actions', label: 'Switch light / dark mode', icon: Moon, run: toggleTheme },
    ...bills.filter(b => (b.status === 'pending_review' && canReview) || (b.status === 'pending_approval' && canApprove(b, role, userId))).map(b => ({ group: 'Waiting on you', label: `${b.status === 'pending_review' ? 'Review' : 'Approve'} ${b.vendor || 'bill'} · ${money(b.amount)}`, icon: Wallet, run: () => b.status === 'pending_review' ? void openBill(b.id) : router.push('/bills') })),
    ...ASK_SUGGESTIONS.map(q => ({ group: 'Ask your books', label: q, icon: Sparkles, run: () => openAsk(q) })),
    ...nav.map(n => ({ group: 'Go to', label: n.name, icon: n.icon, hint: n.path, run: () => router.push(n.path) })),
    ...SUBNAV.flat().filter(n => n.path !== '/rules' || (roleLoaded && canManageRules(role))).map(n => ({ group: 'Go to', label: n.name, icon: n.icon, hint: n.path, run: () => router.push(n.path) })),
    ...docs.slice(0, 60).map(d => ({ group: 'Documents', label: d.filename, icon: FileText, hint: d.vendorName, run: () => void openDoc(d.id) })),
  ], [bills, docs, period, openAsk, router, canUpload, canReview, role, roleLoaded, userId, exportPackage, openBill, openDoc]);
  return <div className="app-shell">
    <div className="backdrop" aria-hidden="true"><i /><i /><i /></div>
    <aside className="sidebar">
      <Link className="brand" href="/"><span className="brand-icon otter"><OtterMark size={30} /></span><span><strong>Otter</strong><small>Harbor Point Wealth</small></span></Link>
      <nav aria-label="Main">{nav.map(item => { const active = isActive(item.match, path); const count = counts[item.path] ?? 0; return <Link className={`nav-item ${active ? 'active' : ''}`} aria-current={active ? 'page' : undefined} href={item.path} key={item.path}><item.icon size={19} /><span>{item.name}</span>{count > 0 && <span className="nav-count" aria-label={`${count} need attention`}>{count}</span>}</Link>; })}</nav>
      <div className="sidebar-bottom">
        <button className="side-link" onClick={() => openAsk()}><Sparkles size={18} />Ask your books</button>
        {roleLoaded && canManageRules(role) && <Link className={`side-link ${path === '/rules' ? 'active' : ''}`} href="/rules"><SlidersHorizontal size={18} />Rules</Link>}
        {signOut && <button className="side-link" onClick={signOut}><LogOut size={18} />Sign out</button>}
      </div>
    </aside>
    <div className="main-area"><header className="topbar">
        <button className="topbar-search" onClick={() => setPalette(true)} aria-label="Search, ask or jump to a page"><Search size={18} /><span>Search, ask, or jump…</span><kbd>⌘K</kbd></button>
        <div className="topbar-right">
          {canUpload && <Link className="icon-button" href="/documents?upload=1" aria-label="Upload a document" title="Upload a document"><Plus size={19} /></Link>}
          <div className="topbar-chip"><ProfileSettings name={userName} role={label(role)} /></div></div></header>
      <main className="content">{USE_LOCAL_API && <div className="alert">Local sample data: financials, reconciliation, Ask and export use D’s server. Uploads and approvals are unavailable.</div>}
        {error && <div role="alert" className="alert error">{error}<Button variant="outline" onClick={() => { setLoading(true); void refresh(); }}>Retry</Button></div>}
        {subnav && <nav className="subnav" aria-label="Section">{subnav.map(item => <Link key={item.path} href={item.path} className={path === item.path ? 'active' : ''} aria-current={path === item.path ? 'page' : undefined}><item.icon size={15} />{item.name}</Link>)}</nav>}
        {loading ? <div className="skeleton-grid" aria-label="Loading practice data">{[1, 2, 3, 4, 5, 6].map(n => <div key={n} className="skeleton" />)}</div> : <>
          {path === '/' && financials && <Dashboard userName={userName} userId={userId} role={role} canUpload={canUpload} canReview={canReview} data={financials} bills={bills} revenue={revenue} period={period} setPeriod={setPeriod} exportPackage={exportPackage} exporting={busy === 'export'} openAsk={openAsk} openBill={openBill} />}
          {path === '/documents' && <Suspense fallback={<Empty text="Loading documents..." />}><DocumentsPage documents={docs} vendors={vendors} bills={bills} openDoc={openDoc} openBill={openBill} onUpload={doc => { setSelected(doc); void refresh(); }} notify={setToast} exportPackage={exportPackage} exporting={busy === 'export'} legacyUpload={pathname === '/inbox'} canUpload={canUpload} canReview={canReview} /></Suspense>}
          {path === '/bills' && <><PageHeading eyebrow="MONEY OUT" title="Bills & approvals" description="Every payment, with the right checks in place." action={canUpload && <Link className="button primary" href="/documents?upload=1"><Plus size={16} /> Upload a bill</Link>} /><div className="summary-strip"><span><strong>{pending.length}</strong> awaiting your approval</span><span><strong>{money(pending.reduce((s, b) => s + b.amount, 0))}</strong> your pending total</span><span><ShieldCheck size={16} /> Payments are simulated</span></div><BillsTable bills={bills} role={role} userId={userId} busy={busy} decide={decide} openDoc={openDoc} openBill={openBill} /></>}
          {path === '/revenue' && revenue && <Revenue data={revenue} openDoc={openDoc} />}
          {path === '/rules' && (roleLoaded && canManageRules(role) ? <Rules rules={rules} notify={setToast} refresh={refresh} /> : <Empty text="Only the owner can manage approval rules." />)}
          {path === '/transactions' && <Transactions notify={setToast} openDoc={openDoc} canImport={canImport} />}
          {path.startsWith('/documents/') && <DocumentRoute id={decodeURIComponent(path.split('/')[2] ?? '')} role={role} />}
          {!ROUTES.includes(path) && !path.startsWith('/documents/') && <Empty text="This page does not exist." />}
        </>}
        <footer className="footer"><span><ShieldCheck size={13} /> {USE_MOCKS ? 'Sample workspace · fictional data' : 'Secure practice workspace'}</span><span>Made for the business behind your advice.</span></footer>
      </main>
    </div>
    {!askOpen && <button className="ask-fab" onClick={() => openAsk()} aria-label="Ask your books"><Sparkles size={18} />Ask</button>}
    <aside className={`ask-panel ${askOpen ? 'open' : ''}`} aria-label="Ask your books" aria-hidden={!askOpen} inert={!askOpen}>
      <div className="ask-panel-heading"><h2><Sparkles size={17} />Ask your books</h2><button aria-label="Close Ask" onClick={() => setAskOpen(false)}><X size={18} /></button></div>
      <Ask openDoc={openDoc} request={askRequest} />
    </aside>
    {palette && <CommandPalette commands={commands} onClose={() => setPalette(false)} onAsk={q => openAsk(q)} />}
    {toast && <div className="toast" role="status"><CircleHelp size={18} /><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast('')}><X size={16} /></button></div>}
    {billDetail && <BillDrawer bill={billDetail} role={role} userId={userId} busy={busy === billDetail.id} onDecide={(decision, comment, changes) => void decide(billDetail, decision, comment, changes)} onClose={() => setBillDetail(undefined)} onConfirmed={() => { setBillDetail(undefined); void refresh(); }} notify={setToast} openDoc={id => { setBillDetail(undefined); void openDoc(id); }} />}
    {selected && <div className="modal-backdrop" onClick={() => setSelected(undefined)}><section className="document-modal" role="dialog" aria-modal="true" aria-label="Document detail" onClick={e => e.stopPropagation()}><div className="modal-title"><strong>Document detail</strong><button autoFocus aria-label="Close document" onClick={() => setSelected(undefined)}><X size={21} /></button></div><DocumentDetail doc={selected} vendors={vendors} role={role} notify={setToast} onResolved={doc => { setSelected(doc); void refresh(); }} /><Button variant="outline" onClick={() => { router.push(`/documents/${selected.id}`); setSelected(undefined); }}>Open full page <ArrowRight size={15} /></Button></section></div>}
  </div>;
}
function toggleTheme() {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('ledgerline-theme', theme); } catch { /* still switches for this visit */ }
  window.dispatchEvent(new Event('ledgerline-theme-change'));
}
type Command = { group: string; label: string; icon: React.ComponentType<{ size?: number }>; hint?: string; run: () => void };
function CommandPalette({ commands, onClose, onAsk }: { commands: Command[]; onClose: () => void; onAsk: (q: string) => void }) {
  const [query, setQuery] = useState(''); const [sel, setSel] = useState(0); const list = useRef<HTMLUListElement>(null);
  const q = query.trim();
  const shown = useMemo<Command[]>(() => { const matches = commands.filter(c => `${c.label} ${c.hint ?? ''}`.toLowerCase().includes(q.toLowerCase())).slice(0, 30); return q ? [...matches, { group: 'Ask your books', label: `Ask: “${q}”`, icon: Sparkles, run: () => onAsk(q) }] : matches; }, [commands, q, onAsk]);
  useEffect(() => { list.current?.querySelector('.selected')?.scrollIntoView({ block: 'nearest' }); }, [sel]);
  const run = (c?: Command) => { if (!c) return; onClose(); c.run(); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(i => Math.min(i + 1, shown.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(i => Math.max(i - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); run(shown[sel]); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };
  let lastGroup = '';
  return <div className="palette-scrim" onClick={onClose}><div className="palette" role="dialog" aria-modal="true" aria-label="Command menu" onClick={e => e.stopPropagation()}>
    <input autoFocus value={query} onChange={e => { setQuery(e.target.value); setSel(0); }} onKeyDown={onKey} placeholder="Search, ask, or jump to a page…" aria-label="Command" role="combobox" aria-expanded="true" aria-controls="palette-list" />
    <ul id="palette-list" ref={list} role="listbox">{shown.map((c, i) => { const heading = c.group !== lastGroup ? c.group : ''; lastGroup = c.group; return <li key={`${c.group}-${c.label}-${i}`}>{heading && <div className="palette-group">{heading}</div>}<button role="option" aria-selected={i === sel} className={i === sel ? 'selected' : ''} onMouseMove={() => setSel(i)} onClick={() => run(c)}><c.icon size={16} /><span>{c.label}</span>{c.hint && <small>{c.hint}</small>}</button></li>; })}</ul>
    <div className="palette-foot"><span><kbd>↑↓</kbd>move</span><span><kbd>↵</kbd>open</span><span><kbd>esc</kbd>close</span></div>
  </div></div>;
}
function greeting() { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'; }
// Who may approve: the owner always; otherwise a role listed on the bill (partner by default). The API enforces the same.
function canApprove(bill: Bill, role: Role, userId = '') {
  return canApproveBill(role, bill.requiredApprovers, bill.createdBy, userId);
}
const approverNames = (bill: Bill) => (bill.requiredApprovers?.length ? bill.requiredApprovers : ['owner']).map(label).join(' or ');
function decisionError(e: unknown) {
  const text = message(e);
  if (/403|forbidden|not allowed|own/i.test(text)) return 'You can’t approve this one: either your role can’t, or you uploaded it yourself (segregation of duties). Ask another approver.';
  if (/409|already/i.test(text)) return 'Someone already decided this bill. Refreshing.';
  return text;
}
function message(e: unknown) { return e instanceof Error ? e.message : 'Something went wrong. Please try again.'; }
function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) { return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>; }
function Empty({ text }: { text: string }) { return <div className="empty"><FolderOpen size={26} /><p>{text}</p></div>; }
function Pill({ status }: { status: string }) { return <span className={`pill ${status}`}><span />{label(status)}</span>; }

function Dashboard({ userName, userId, role, canUpload, canReview, data, bills, revenue, period, setPeriod, exportPackage, exporting, openAsk, openBill }: { userName: string; userId: string; role: Role; canUpload: boolean; canReview: boolean; data: Financials; bills: Bill[]; revenue?: Reconciliation; period: string; setPeriod: (p: string) => void; exportPackage: () => void; exporting: boolean; openAsk: (q?: string) => void; openBill: (id: string) => void }) {
  const [tab, setTab] = useState('Income statement');
  const pending = bills.filter(b => (b.status === 'pending_approval' && canApprove(b, role, userId)) || (b.status === 'pending_review' && canReview));
  // Revenue follow-ups (upload a missing statement, chase a short payout) belong to the owner and ops.
  const revenueItems = revenue && canUpload ? (statementMissing(revenue) ? 1 : revenue.flags.length) : 0;
  const prevMargin = data.kpis.previous?.margin; const marginDelta = data.kpis.margin !== null && typeof prevMargin === 'number' ? (data.kpis.margin - prevMargin) * 100 : null;
  return <><PageHeading eyebrow="HOME" title={`${greeting()}, ${userName.split(' ')[0]}`} description="Here's how Harbor Point is doing." action={<div className="heading-actions"><select aria-label="Financial period" value={period} onChange={e => setPeriod(e.target.value)}>{USE_MOCKS && !USE_LOCAL_API ? <option value="2026-Q3">Q3 2026 · Jul – Sep</option> : <><option value="2026-Q3">Q3 2026 · Jul – Sep</option><option value="2026-08">August 2026</option><option value="2026-07">July 2026</option><option value="2026-Q2">Q2 2026 · Apr – Jun</option><option value="2026">2026 year to date</option></>}</select></div>} />
    <div className="home-grid"><div className="home-main">
      <section className="panel hero-card"><div className="hero-top"><span className="label">Est. practice value <span title={data.valuation.method}><CircleHelp size={14} /></span></span><span className="chip">{USE_MOCKS ? 'Sample data' : 'Built on recurring revenue'}</span></div>
        <div className="hero-num"><span><Amount value={data.valuation.mid} /></span><span className="delta up">{percent(data.kpis.recurringPct)} recurring</span></div>
        <p className="hero-sub">{money(data.valuation.low)} – {money(data.valuation.high)} estimated range</p>
        <div className="hero-actions">{canUpload && <Link className="button primary" href="/documents?upload=1"><ArrowUp size={16} />Upload document</Link>}<Link className="button outline" href="/bills"><Check size={16} />Review bills{pending.length ? ` (${pending.length})` : ''}</Link><Button variant="outline" disabled={exporting} onClick={exportPackage}><ArrowDownToLine size={16} />{exporting ? 'Preparing…' : 'Export package'}</Button><Button variant="outline" onClick={() => openAsk()}><Sparkles size={16} />Ask your books</Button></div></section>
      <div className="mini-grid"><Kpi label="Money in" tone="in" icon={<ArrowDown size={16} />} href="/revenue" value={<Amount value={data.pnl.totalRevenue} />} note="Revenue for the period" /><Kpi label="Money out" tone="out" icon={<ArrowUp size={16} />} href="/bills" value={<Amount value={data.pnl.totalExpenses} />} note="Expenses for the period" /><Kpi label="Operating margin" icon={<Wallet size={16} />} value={percent(data.kpis.margin)} note={marginDelta === null ? `${money(data.pnl.operatingIncome)} operating income` : `${marginDelta >= 0 ? '+' : ''}${marginDelta.toFixed(1)} pts vs ${data.kpis.previous.period}`} /></div>
      <section className="panel chart-panel"><div className="panel-heading"><div><h2>Financial statements</h2><p>Income statement, balance sheet and cash flow for the selected period.</p></div><span className="muted">USD</span></div><div className="tabs" role="tablist">{['Income statement', 'Balance sheet', 'Cash flow'].map(name => <button role="tab" aria-selected={tab === name} className={tab === name ? 'selected' : ''} key={name} onClick={() => setTab(name)}>{name}</button>)}</div>{tab === 'Income statement' ? <>{data.monthly?.length ? <><div className="chart-legend"><span><i className="green" /> Revenue</span><span><i className="gray" /> Expenses</span><span className="chart-period">Last {data.monthly.length} months</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.monthly} margin={{ top: 16, right: 16, left: 4, bottom: 0 }}><defs><linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--chart-1)" stopOpacity={.12} /><stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} /></linearGradient><linearGradient id="expFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--chart-2)" stopOpacity={.28} /><stop offset="100%" stopColor="var(--accent)" stopOpacity={0} /></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--chart-grid)" /><XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: 'var(--muted)' }} dy={10} /><YAxis axisLine={false} tickLine={false} width={56} tickFormatter={v => `$${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fill: 'var(--faint)' }} /><Tooltip formatter={value => money(Number(value))} contentStyle={{ background: 'var(--surface)', borderColor: 'var(--line)', color: 'var(--ink)', borderRadius: 8, fontSize: 12 }} itemStyle={{ color: 'var(--ink)' }} cursor={{ stroke: 'var(--line-strong)' }} /><Area type="monotone" dataKey="revenue" name="Revenue" stroke="var(--chart-1)" strokeWidth={2} fill="url(#revFill)" dot={false} activeDot={{ r: 4 }} /><Area type="monotone" dataKey="expenses" name="Expenses" stroke="var(--chart-2)" strokeWidth={2} fill="url(#expFill)" dot={false} activeDot={{ r: 4 }} /></AreaChart></ResponsiveContainer></div></> : <><div className="chart-legend"><span><i className="green" /> Revenue</span><span><i className="gray" /> Expenses</span><span className="chart-period">Selected period totals</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={[{ name: 'Revenue', amount: data.pnl.totalRevenue }, { name: 'Expenses', amount: data.pnl.totalExpenses }, { name: 'Operating income', amount: data.pnl.operatingIncome }]} margin={{ top: 15, right: 12, left: 4, bottom: 0 }}><CartesianGrid vertical={false} stroke="var(--chart-grid)" /><XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: 'var(--muted)' }} dy={10} /><YAxis axisLine={false} tickLine={false} width={56} tickFormatter={v => `$${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fill: 'var(--faint)' }} /><Tooltip formatter={value => money(Number(value))} contentStyle={{ background: 'var(--surface)', borderColor: 'var(--line)', color: 'var(--ink)', borderRadius: 8, fontSize: 12 }} itemStyle={{ color: 'var(--ink)' }} cursor={{ fill: 'var(--hover)' }} /><Bar dataKey="amount" name="Amount" radius={[5, 5, 0, 0]} maxBarSize={56}><Cell fill="var(--chart-1)" /><Cell fill="var(--chart-2)" /><Cell fill="var(--faint)" /></Bar></BarChart></ResponsiveContainer></div></>}<FinancialStatement data={data} tab={tab} /><div className="chart-bottom"><span>Operating income <strong>{money(data.pnl.operatingIncome)}</strong></span><button onClick={() => openAsk()}>Explore your numbers <ArrowRight size={14} /></button></div></> : <FinancialStatement data={data} tab={tab} />}</section>
      <section className="panel recent-panel"><div className="panel-heading"><div><h2>Recent bills</h2><p>The latest in your back office.</p></div><Link href="/bills">View all</Link></div><div className="table-scroll"><table><thead><tr><th>Vendor</th><th>Category</th><th>Amount</th><th>Status</th></tr></thead><tbody>{bills.slice(0, 4).map(b => <tr key={b.id}><td><span className="vendor-cell"><span className="vendor-avatar">{b.vendor.slice(0, 2).toUpperCase()}</span>{b.vendor}</span></td><td className="muted">{b.glAccount.split('·')[1] ?? b.glAccount}</td><td className="amount">{cents(b.amount)}</td><td><Pill status={b.status} /></td></tr>)}</tbody></table></div></section>
    </div><div className="home-side">
      <section className="panel attention-panel"><div className="panel-heading"><div><h2>Waiting on you</h2><p>A little action goes a long way.</p></div><span className="count-bubble">{pending.length + revenueItems}</span></div><div className="queue">{pending.slice(0, 3).map(bill => bill.status === 'pending_review' ? <button className="attention-item" key={bill.id} onClick={() => openBill(bill.id)}><span className="attention-icon amber"><FileText size={17} /></span><div><strong>{bill.vendor || 'Unknown vendor'}</strong><p>Review extracted fields <i>·</i> {money(bill.amount)}</p></div><ArrowRight size={15} /></button> : <button className="attention-item" key={bill.id} onClick={() => openBill(bill.id)}><span className="attention-icon amber"><Wallet size={17} /></span><div><strong>{bill.vendor}</strong><p>{canApprove(bill, role, userId) ? 'Awaiting your approval' : `Pending ${approverNames(bill)} approval`} <i>·</i> {money(bill.amount)}</p>{bill.ruleHits[0] && <small>{bill.ruleHits[0]}</small>}</div><ArrowRight size={15} /></button>)}{!revenueItems ? null : revenue && statementMissing(revenue) ? <Link className="attention-item" href="/revenue"><span className="attention-icon coral"><ArrowDown size={17} /></span><div><strong>Payout statement not uploaded</strong><small>Upload this month’s LPL statement to reconcile {money(revenue.expected)} of expected revenue.</small></div><ArrowRight size={15} /></Link> : revenue?.flags.map(flag => <Link className="attention-item" href="/revenue" key={flag.lineId}><span className="attention-icon coral"><ArrowDown size={17} /></span><div><strong>{revenue.lines.find(line => line.id === flag.lineId)?.label ?? 'Revenue variance'}</strong><small className={flag.severity === 'high' ? 'text-red' : ''}>{flag.message}</small></div><ArrowRight size={15} /></Link>)}{pending.length === 0 && !revenueItems && <Empty text="You're all caught up." />}</div><Link href="/bills" className="panel-bottom-link">View all bills <ArrowRight size={14} /></Link></section>
      <section className="insight-card"><span className="insight-icon"><Sparkles size={19} /></span><h2>Ask your books</h2><p>Answers grounded in your documents, with sources.</p><div className="suggestions">{ASK_SUGGESTIONS.map(q => <button key={q} className="suggestion" onClick={() => openAsk(q)}>{q}<ArrowUpRight size={15} /></button>)}</div></section>
    </div></div>
  </>;
}
function Kpi({ label: title, value, note, icon, tone, href }: { label: string; value: React.ReactNode; note: string; icon: React.ReactNode; tone?: 'in' | 'out'; href?: string }) {
  const body = <><div className="kpi-label"><span className={`ico ${tone ?? ''}`}>{icon}</span>{title}{href && <ArrowUpRight className="go" size={16} />}</div><div className="kpi-value">{value}</div><div className="kpi-note">{note}</div></>;
  return href ? <Link className="kpi" href={href}>{body}</Link> : <section className="kpi">{body}</section>;
}

function Upload({ onComplete, notify }: { onComplete: (doc: Document) => void; notify: (text: string) => void }) {
  const input = useRef<HTMLInputElement>(null); const abort = useRef<AbortController | null>(null); const [status, setStatus] = useState(''); const [dragging, setDragging] = useState(false);
  const [driveBusy, setDriveBusy] = useState(false);
  const processFile = async (file: File, progress: (status: string) => void, signal: AbortSignal) => {
    const doc = await api.upload(file, progress, signal);
    signal.throwIfAborted(); onComplete(doc);
  };
  useEffect(() => () => abort.current?.abort(), []);
  const upload = async (file?: File) => { if (!file || status || driveBusy || USE_LOCAL_API) return; abort.current = new AbortController(); setStatus('Uploading'); try { await processFile(file, setStatus, abort.current.signal); notify(USE_MOCKS ? 'Demo document created using sample fields. Uploaded file retained for preview.' : 'Document processed successfully.'); } catch (e) { if (!abort.current.signal.aborted) notify(message(e)); } finally { setStatus(''); if (input.current) input.current.value = ''; } };
  return <section className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); void upload(e.dataTransfer.files[0]); }}><span className="upload-icon">{status ? <LoaderCircle className="spin" size={30} /> : <UploadCloud size={30} />}</span><h2>{status || 'Give your paperwork a place to land.'}</h2><p>Drag and drop an invoice, receipt, payout statement, W-9 or void check.</p><Button onClick={() => input.current?.click()} disabled={Boolean(status) || driveBusy || USE_LOCAL_API}><Plus size={16} /> Choose a document</Button><GoogleDriveImport disabled={Boolean(status) || USE_LOCAL_API} onBusy={setDriveBusy} upload={processFile} notify={notify} /><input ref={input} type="file" accept="application/pdf,image/png,image/jpeg" hidden onChange={e => void upload(e.target.files?.[0])} /><small>PDF, PNG or JPG · up to 20 MB {USE_MOCKS && '· Demo fields are simulated'}</small></section>;
}
function DocumentTable({ documents, openDoc, title = 'Documents', emptyText = 'No documents found. Try another filter or upload a file.' }: { documents: Document[]; openDoc: (id: string) => void; title?: string; emptyText?: string }) { return <section className="panel"><div className="panel-heading"><h2>{title} <span className="muted">({documents.length})</span></h2></div>{documents.length ? <div className="table-scroll"><table><thead><tr><th>Document</th><th>Type</th><th>Vendor</th><th>Uploaded</th><th>Amount</th><th>Status</th></tr></thead><tbody>{documents.map(doc => <tr key={doc.id}><td><button className="document-link" onClick={() => openDoc(doc.id)}><FileText size={17} />{doc.filename}</button></td><td>{label(doc.type)}</td><td>{doc.vendorName}</td><td className="nowrap">{doc.createdAt.slice(0, 10)}</td><td>{['w9', 'void_check'].includes(doc.type) || !Number.isFinite(doc.amount) ? '—' : money(doc.amount)}</td><td><Pill status={doc.status} /></td></tr>)}</tbody></table></div> : <Empty text={emptyText} />}</section>; }
function BillsTable({ bills, role, userId, busy, decide, openDoc, openBill }: { bills: Bill[]; role: Role; userId: string; busy: string; decide: (bill: Bill, decision: 'approve' | 'reject') => void; openDoc: (id: string) => void; openBill: (id: string) => void }) {
  const [filter, setFilter] = useState('all'); const filtered = bills.filter(b => filter === 'all' || b.status === filter);
  return <section className="panel"><div className="panel-heading"><h2>All bills</h2><select aria-label="Bill status" value={filter} onChange={e => setFilter(e.target.value)}>{['all', 'pending_approval', 'pending_review', 'pending_docs', 'processing', 'scheduled', 'rejected'].map(s => <option key={s} value={s}>{label(s)}</option>)}</select></div><div className="table-scroll"><table><thead><tr><th>Vendor / rules</th><th>Amount</th><th>Due date</th><th>Status</th><th>Decision</th></tr></thead><tbody>{filtered.map(b => <tr key={b.id}><td><button className="document-link" disabled={!b.docId} onClick={() => b.docId && openDoc(b.docId)}>{b.vendor}</button><small className="table-sub">{b.glAccount}{b.invoiceNumber ? ` · ${b.invoiceNumber}` : ''}</small>{b.ruleHits.map(hit => <small className="rule-hit" key={hit}>{hit}</small>)}<button className="document-link history-link" disabled={busy === b.id} onClick={() => openBill(b.id)}>Details & history</button></td><td className="nowrap">{money(b.amount)}</td><td className="nowrap">{b.dueDate}</td><td><Pill status={b.status} /></td><td>{b.status === 'pending_approval' ? (canApprove(b, role, userId) ? <Button disabled={busy === b.id} onClick={() => openBill(b.id)}><Check size={14} />Review & approve</Button> : <span className="muted">Pending {approverNames(b)} approval</span>) : b.status === 'pending_review' ? (canReviewDocuments(role) ? <Button variant="outline" disabled={busy === b.id} onClick={() => openBill(b.id)}>Review fields</Button> : <span className="muted">Awaiting operations review</span>) : b.status === 'pending_docs' ? <span className="muted">Waiting for vendor documents</span> : b.status === 'processing' ? <span className="muted">Running checks…</span> : <span className="muted">{b.status === 'scheduled' ? 'Mock payment' : 'Decision recorded'}</span>}</td></tr>)}</tbody></table></div>{!filtered.length && <Empty text="No bills with this status." />}</section>;
}
function DocumentsPage({ documents: records, vendors, bills, openDoc, openBill, onUpload, notify, exportPackage, exporting, legacyUpload, canUpload, canReview }: { documents: Document[]; vendors: Vendor[]; bills: Bill[]; openDoc: (id: string) => void; openBill: (id: string) => void; onUpload: (doc: Document) => void; notify: (text: string) => void; exportPackage: () => void; exporting: boolean; legacyUpload: boolean; canUpload: boolean; canReview: boolean }) {
  const documents = records.map(doc => ({ ...doc, id: doc.id || (doc as Document & { documentId?: string }).documentId || doc.filename }));
  const [view, setView] = useState('all');
  const resultsSection = useRef<HTMLElement>(null);
  const [query, setQuery] = useState(''); const [type, setType] = useState('all'); const [vendor, setVendor] = useState('all'); const [date, setDate] = useState(''); const [status, setStatus] = useState('all');
  const needsReview = (doc: Document) => {
    if (['needs_review', 'pending_review', 'failed', 'error'].includes(doc.status)) return true;
    const bill = bills.find(b => (b.docId && b.docId === doc.id) || (doc.billId && b.id && b.id === doc.billId));
    if (bill && ['approved', 'scheduled', 'rejected'].includes(bill.status)) return false;
    return bill?.status === 'pending_review' || (!USE_LOCAL_API && doc.status === 'processed' && !doc.review && typeof doc.confidence === 'number' && doc.confidence < .8);
  };
  const reviewCount = documents.filter(needsReview).length;
  const isProcessing = (doc: Document) => ['processing', 'uploaded', 'extracting', 'queued', 'pending'].includes(doc.status);
  const processingCount = documents.filter(isProcessing).length;
  const filtered = documents.filter(d => (view !== 'review' || needsReview(d)) && (view !== 'processing' || isProcessing(d)) && `${d.filename} ${d.vendorName}`.toLowerCase().includes(query.toLowerCase()) && (type === 'all' || d.type === type) && (vendor === 'all' || d.vendorName === vendor) && (status === 'all' || d.status === status) && (!date || d.createdAt.slice(0, 10) >= date)).sort((a, b) => b.createdAt.localeCompare(a.createdAt) || a.filename.localeCompare(b.filename));
  return <>
    <div className="page-heading"><div><div className="eyebrow">YOUR DOCUMENTS</div><h1>Documents</h1></div></div>
    {canUpload && <section id="document-upload" className="documents-upload"><div className="documents-upload-heading"><h2>Upload a document</h2></div><Upload onComplete={onUpload} notify={notify} /></section>}
    <section id="document-results" ref={resultsSection} className="document-results" tabIndex={-1} aria-label="Document results">
    <div className="tabs documents-tabs" role="group" aria-label="Document views">{[{ id: 'all', name: 'All documents' }, { id: 'review', name: `Needs review (${reviewCount})` }, { id: 'processing', name: `Processing (${processingCount})` }, { id: 'vendors', name: 'Vendors' }].map(tab => <button key={tab.id} className={view === tab.id ? 'selected' : ''} aria-pressed={view === tab.id} onClick={() => setView(tab.id)}>{tab.name}</button>)}</div>
    {view === 'vendors' ? <section className="panel vendor-panel"><div className="panel-heading"><h2>Vendors</h2><span className="muted">{vendors.length} vendor records</span></div>{vendors.length ? <div className="table-scroll"><table><thead><tr><th>Vendor</th><th>Default account</th><th>W-9</th><th>Void check</th><th>Bills</th></tr></thead><tbody>{vendors.map(v => <tr key={v.id || v.name}><td>{v.name}{v.bankDetailReviewRequired && <small className="rule-hit">Potential shared bank details - verify with {v.possibleDuplicateVendorNames?.join(', ')}. Last four digits alone are not conclusive.</small>}</td><td>{v.defaultGlAccount}</td><td>{v.hasW9 ? 'On file' : 'Missing'}</td><td>{v.hasVoidCheck ? 'On file' : 'Missing'}</td><td>{v.billCount}</td></tr>)}</tbody></table></div> : <Empty text="No vendor records yet." />}</section> : <>
      <div className="filters"><label className="search-field"><Search size={17} /><input aria-label="Search documents" placeholder="Search documents or vendors..." value={query} onChange={e => setQuery(e.target.value)} /></label><select aria-label="Document type" value={type} onChange={e => setType(e.target.value)}>{['all', 'invoice', 'receipt', 'payout_statement', 'w9', 'void_check'].map(t => <option key={t} value={t}>{t === 'all' ? 'All types' : label(t)}</option>)}</select><select aria-label="Vendor filter" value={vendor} onChange={e => setVendor(e.target.value)}><option value="all">All vendors</option>{Array.from(new Set(documents.map(d => d.vendorName).filter(Boolean))).sort().map(v => <option key={v}>{v}</option>)}</select><select aria-label="Document status" value={status} onChange={e => setStatus(e.target.value)}><option value="all">All statuses</option>{Array.from(new Set(documents.map(d => d.status))).sort().map(s => <option key={s} value={s}>{label(s)}</option>)}</select><input aria-label="Documents from date" type="date" value={date} onChange={e => setDate(e.target.value)} /></div>
      <DocumentTable documents={filtered} openDoc={openDoc} title={view === 'review' ? 'Needs review' : view === 'processing' ? 'Processing' : 'All documents'} />
      {view === 'review' && bills.some(b => b.status === 'pending_review') && <section className="panel vendor-panel"><div className="panel-heading"><h2>Review bill fields</h2></div>{bills.filter(b => b.status === 'pending_review').map(b => <div className="attention-item" key={b.id}><div><strong>{b.vendor || 'Unknown vendor'}</strong><p>{money(b.amount)}</p></div>{canReview ? <Button variant="outline" onClick={() => openBill(b.id)}>Review fields</Button> : <span className="muted">Awaiting operations review</span>}</div>)}</section>}
    </>}
    </section>
  </>;
}
function Ask({ openDoc, request }: { openDoc: (id: string) => void; request?: { q: string; n: number } }) {
  const [question, setQuestion] = useState(''); const [messages, setMessages] = useState<{ question: string; answer: Answer }[]>([]); const [pending, setPending] = useState(false); const [error, setError] = useState('');
  const thread = useRef<HTMLDivElement>(null);
  const send = async (q: string) => { if (!q.trim() || pending) return; setPending(true); setError(''); try { const answer = await api.ask(q.trim()); setMessages(m => [...m, { question: q.trim(), answer }]); setQuestion(''); } catch (e) { setError(message(e)); } finally { setPending(false); } };
  useEffect(() => { if (request) void send(request.q); }, [request?.n]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: 'smooth' }); }, [messages.length, pending]);
  return <section className="chat"><div className="chat-thread" ref={thread} aria-live="polite">{!messages.length && <div className="chat-intro"><p>Ask about expenses, payouts or practice performance. Every answer links to the document it came from.</p><div className="chat-suggestions">{ASK_SUGGESTIONS.map(q => <button key={q} disabled={pending} onClick={() => void send(q)}>{q}<ArrowUpRight size={14} /></button>)}</div></div>}{messages.map((m, i) => <div className="chat-turn" key={i}><p className="question">{m.question}</p><div className="answer"><Sparkles size={16} /><div><p>{m.answer.answer}</p><small className="table-sub">Period: {m.answer.period}</small><div className="citations">{m.answer.citations.map(c => <button key={c.documentId} title={c.snippet} onClick={() => openDoc(c.documentId)}><FileText size={12} />{c.label}<ArrowUpRight size={11} /></button>)}</div></div></div></div>)}{pending && <p className="chat-pending"><LoaderCircle size={16} className="spin" />Looking through your books…</p>}{error && <p role="alert" className="text-red">{error}</p>}</div><form className="chat-input" onSubmit={e => { e.preventDefault(); void send(question); }}><input aria-label="Question about your books" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Why did my margin drop in Q3?" maxLength={2000} /><Button disabled={pending || !question.trim()} aria-label="Send question"><Send size={16} /></Button></form><small className="chat-disclaimer">{USE_LOCAL_API ? 'Local server uses a sample answer unless Bedrock is enabled. ' : USE_MOCKS ? 'Demo answers use fixed sample context. ' : ''}Review cited sources. Answers support bookkeeping decisions.</small></section>;
}
// Names the rules engine understands (backend/src/shared/rules_engine.py) and how to say them.
const RULE_FIELDS: { value: string; label: string; kind: 'number' | 'boolean' }[] = [
  { value: 'bill.amount', label: 'Bill amount', kind: 'number' },
  { value: 'vendor.hasW9', label: 'Vendor has a W-9', kind: 'boolean' },
  { value: 'vendor.hasVoidCheck', label: 'Vendor has a void check', kind: 'boolean' },
  { value: 'bill.received', label: 'Goods or services received', kind: 'boolean' },
];
const RULE_OPS: Record<string, string> = { gt: 'is over', gte: 'is at least', lt: 'is under', lte: 'is at most', eq: 'is', neq: 'is not' };
const FIELD_WORDS: Record<string, string> = { 'bill.amount': 'bill amount', 'bill.documentType': 'document type', 'bill.isDuplicate': 'bill is a duplicate', 'bill.requiresReceipt': 'bill requires a receipt', 'bill.received': 'bill was received', 'vendor.hasW9': 'vendor has a W-9', 'vendor.hasVoidCheck': 'vendor has a void check' };
function describeCondition(c?: RuleCondition): string {
  if (!c) return '';
  if (c.all) return c.all.map(describeCondition).join(' and ');
  if (c.any) return c.any.map(describeCondition).join(' or ');
  if (c.not) return `not (${describeCondition(c.not)})`;
  const field = FIELD_WORDS[c.field ?? ''] ?? c.field ?? '';
  if (typeof c.value === 'boolean') { const yes = (c.op === 'neq') !== c.value; return yes ? field : field.replace(/\b(has|is|was|requires)\b/, m => ({ has: 'has no', is: 'is not', was: 'was not', requires: 'does not require' })[m] ?? m); }
  const value = typeof c.value === 'number' && (c.field ?? '').endsWith('amount') ? money(c.value) : String(c.value);
  return `${field} ${RULE_OPS[c.op ?? ''] ?? c.op} ${value}`;
}
function Rules({ rules, notify, refresh }: { rules: Rule[]; notify: (text: string) => void; refresh: () => Promise<void> }) {
  const [show, setShow] = useState(false); const [busy, setBusy] = useState(false);
  const [field, setField] = useState(RULE_FIELDS[0].value); const [action, setAction] = useState<Rule['action']>('require_approval');
  const [confirming, setConfirming] = useState(''); const [deleting, setDeleting] = useState('');
  const remove = async (rule: Rule) => { setDeleting(rule.id); try { await api.deleteRule(rule.id); setConfirming(''); await refresh(); notify(`Deleted “${rule.name}”. It no longer applies to new bills.`); } catch (err) { notify(message(err)); } finally { setDeleting(''); } };
  const kind = RULE_FIELDS.find(f => f.value === field)?.kind ?? 'number';
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const form = new FormData(e.currentTarget); const raw = String(form.get('value') ?? '');
    const value = kind === 'number' ? Number(raw.replace(/[$,]/g, '')) : raw === 'true';
    if (kind === 'number' && !(value as number > 0)) { notify('Enter an amount greater than 0, like 5000.'); return; }
    const op = String(form.get('op'));
    setBusy(true);
    try {
      await api.createRule({ name: String(form.get('name')), condition: { field, op, value }, action, ...(action === 'require_approval' ? { approverRole: String(form.get('role')) as Role } : {}), reason: String(form.get('name')) });
      setShow(false); await refresh(); notify('Rule created. It applies to new bills from now on.');
    } catch (err) { notify(message(err)); } finally { setBusy(false); }
  };
  return <><PageHeading eyebrow="APPROVAL RULES" title="Your practice. Your guardrails." description="Set the checks that keep your back office running smoothly." action={<Button disabled={USE_LOCAL_API} onClick={() => setShow(!show)}><Plus size={16} />Create rule</Button>} />{show && <form className="panel rule-form" onSubmit={submit}><h2>Create an approval rule</h2><label>Rule name<input name="name" required maxLength={100} placeholder="Bills over $5,000 need the owner" /></label><div className="form-row"><label>When<select name="field" value={field} onChange={e => setField(e.target.value)}>{RULE_FIELDS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}</select></label>{kind === 'number' ? <><label>Is<select name="op" defaultValue="gt"><option value="gt">over</option><option value="gte">at least</option><option value="lt">under</option></select></label><label>Amount ($)<input name="value" required inputMode="decimal" placeholder="5000" /></label></> : <><input type="hidden" name="op" value="eq" /><label>Is<select name="value" defaultValue="false"><option value="false">No</option><option value="true">Yes</option></select></label></>}</div><div className="form-row"><label>Then<select name="action" value={action} onChange={e => setAction(e.target.value as Rule['action'])}><option value="require_approval">Require approval</option><option value="require_docs">Hold until documents arrive</option><option value="block">Block payment</option></select></label>{action === 'require_approval' && <label>Approver<select name="role" defaultValue="partner"><option value="partner">Partner</option><option value="owner">Owner</option></select></label>}</div><Button disabled={busy}>{busy ? 'Saving…' : 'Save rule'}</Button>{USE_MOCKS && <small>Demo rules are stored for display. The sample approval flow uses predefined rules.</small>}</form>}<div className="rule-grid">{rules.map(r => <section className="panel rule-card" key={r.id}><ShieldCheck size={21} /><h2>{r.name}</h2><p>When the {describeCondition(r.condition)}</p>{r.reason && r.reason !== r.name && <small className="table-sub">Shown on bills as: “{r.reason}”</small>}<div><Pill status={r.action} /><span className="muted">{r.approverRole ? `Approver: ${label(r.approverRole)}` : r.action === 'block' ? 'Blocks automatically' : 'Held until documents arrive'}</span></div>{!USE_LOCAL_API && <div className="rule-actions">{confirming === r.id ? <><span className="muted">Delete this rule?</span><Button variant="outline" disabled={deleting === r.id} onClick={() => void remove(r)}>{deleting === r.id ? 'Deleting…' : 'Yes, delete'}</Button><Button variant="outline" disabled={deleting === r.id} onClick={() => setConfirming('')}>Cancel</Button></> : <Button variant="outline" aria-label={`Delete rule ${r.name}`} onClick={() => setConfirming(r.id)}><Trash2 size={14} />Delete</Button>}</div>}</section>)}</div></>;
}
function Transactions({ notify, openDoc, canImport }: { notify: (text: string) => void; openDoc: (id: string) => void; canImport: boolean }) {
  const [busy, setBusy] = useState(false); const [txns, setTxns] = useState<CardTransaction[]>(); const [loadError, setLoadError] = useState('');
  const load = useCallback(() => api.transactions().then(list => { setTxns(list); setLoadError(''); }).catch(e => { setTxns([]); setLoadError(message(e)); }), []);
  useEffect(() => { void load(); }, [load]);
  const total = (txns ?? []).reduce((sum, t) => sum + t.amount, 0);
  return <><PageHeading eyebrow="CARD TRANSACTIONS" title="Bring your spending into view." description={canImport ? 'Import your card statement. Each charge is categorized and matched to its receipt.' : 'Review card charges and their matched receipts.'} />{canImport && <section className="panel rule-form"><h2>Import a card statement</h2><p>{USE_MOCKS ? 'CSV import is available when the backend endpoint is connected.' : 'A CSV with Date, Description and Amount columns (Card is optional). Re-importing the same file never books a charge twice.'}</p><input aria-label="Transaction CSV" type="file" accept=".csv,text/csv" disabled={busy || USE_MOCKS || USE_LOCAL_API} onChange={async e => { const file = e.target.files?.[0]; if (!file) return; setBusy(true); try { const result = await api.importTransactions(file); notify(`${result.imported} imported · ${result.categorized} categorized · ${result.matchedReceipts} receipts matched`); await load(); } catch (err) { notify(message(err)); } finally { setBusy(false); e.target.value = ''; } }} /></section>}
    <section className="panel"><div className="panel-heading"><h2>Charges <span className="muted">({txns?.length ?? 0})</span></h2><span className="muted">{cents(total)} total</span></div>{loadError && <div className="alert">Couldn’t load charges: {loadError}</div>}{txns === undefined ? <div className="skeleton" /> : txns.length ? <div className="table-scroll"><table><thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Amount</th><th>Receipt</th></tr></thead><tbody>{txns.map(t => <tr key={t.txnId}><td>{t.date}</td><td>{t.description}</td><td><small className="table-sub">{t.glAccount} · {t.glAccountName}</small>{t.categoryReason && <small className="table-sub">{t.categoryReason}</small>}</td><td>{cents(t.amount)}</td><td>{t.receiptDocumentId ? <button className="document-link" onClick={() => openDoc(t.receiptDocumentId!)}>Matched <ArrowUpRight size={13} /></button> : <span className="muted">No receipt yet</span>}</td></tr>)}</tbody></table></div> : <Empty text="No card charges yet. Import a statement to see them here." />}</section></>;
}
function DocumentRoute({ id, role }: { id: string; role: Role }) { const [doc, setDoc] = useState<Document>(); const [vendors, setVendors] = useState<Vendor[]>([]); const [error, setError] = useState(''); useEffect(() => { let active = true; Promise.all([api.document(id), api.vendors()]).then(([d, v]) => { if (active) { setDoc(d); setVendors(v); } }).catch(e => { if (active) setError(message(e)); }); return () => { active = false; }; }, [id]); return error ? <div className="alert error">{error}</div> : doc ? <><PageHeading eyebrow="DOCUMENT DETAIL" title={doc.filename} description="Source document and extracted information, side by side." /><DocumentDetail doc={doc} vendors={vendors} role={role} /></> : <div className="skeleton" />; }
// Needs-review documents without a bill are resolved by operations or the owner.
function ResolveDocument({ doc, role, notify, onResolved }: { doc: Document; role?: Role; notify?: (text: string) => void; onResolved?: (doc: Document) => void }) {
  const [note, setNote] = useState(''); const [busy, setBusy] = useState('');
  const allowed = role === 'owner' || role === 'ops';
  const resolve = async (resolution: 'accept' | 'dismiss') => { setBusy(resolution); try { const updated = await api.resolveDocument(doc.id, resolution, note.trim()); notify?.(resolution === 'accept' ? 'Marked as reviewed. The fields are confirmed.' : 'Dismissed. Kept in the library; nothing was posted.'); onResolved?.(updated); } catch (e) { notify?.(message(e)); } finally { setBusy(''); } };
  return <div className="resolve-panel">
    <strong>Finish the review</strong>
    <p className="muted">{typeof doc.confidence === 'number' ? `The AI was ${Math.round(doc.confidence * 100)}% sure about this one. ` : ''}Compare the fields with the document, then close it out.</p>
    {allowed ? <>
      <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} maxLength={500} placeholder="Note (optional), e.g. Duplicate of Maya's upload" aria-label="Review note" />
      <div className="decision-buttons"><Button disabled={Boolean(busy)} onClick={() => void resolve('accept')}><Check size={15} />{busy === 'accept' ? 'Saving…' : 'Fields are correct'}</Button><Button variant="outline" disabled={Boolean(busy)} onClick={() => void resolve('dismiss')}>{busy === 'dismiss' ? 'Saving…' : 'Not a financial record'}</Button></div>
    </> : <p className="muted">Document review is done by Operations or the owner. Partners approve bills.</p>}
  </div>;
}
function DocumentDetail({ doc, vendors, role, notify, onResolved }: { doc: Document; vendors: Vendor[]; role?: Role; notify?: (text: string) => void; onResolved?: (doc: Document) => void }) { const recognized = vendors.find(v => v.name === doc.vendorName && v.billCount > 1); return <div className="document-detail"><div className="preview">{doc.viewUrl ? doc.viewUrl.startsWith('blob:') && /\.(png|jpe?g)$/i.test(doc.filename) ? <img src={doc.viewUrl} alt={doc.filename} /> : <iframe title={`Preview of ${doc.filename}`} src={doc.viewUrl} /> : <Empty text="Preview is not available yet." />}</div><section className="extracted"><div className="eyebrow">{USE_LOCAL_API ? 'SOURCE METADATA' : 'EXTRACTED INFORMATION'}</div><h2>{doc.vendorName || label(doc.type)}</h2><div className="document-badges"><Pill status={doc.status} />{!USE_LOCAL_API && typeof doc.confidence === 'number' && <span className={`pill ${doc.confidence >= .8 ? 'processed' : 'pending_review'}`}>{Math.round(doc.confidence * 100)}% confidence</span>}</div>{recognized && <div className="recognized"><Check size={15} />Recognized vendor · {recognized.billCount} prior bills</div>}{!USE_LOCAL_API && doc.status === 'needs_review' && !doc.billId ? <ResolveDocument doc={doc} role={role} notify={notify} onResolved={onResolved} /> : !USE_LOCAL_API && doc.status === 'needs_review' && typeof doc.confidence === 'number' && doc.confidence < .8 && <div className="alert">Low confidence. Operations should verify these fields before bill creation or approval.</div>}<dl>{Object.entries(doc.extracted ?? {}).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>{doc.viewUrl && <a className="document-link" href={doc.viewUrl} target="_blank" rel="noreferrer">Open original <ArrowUpRight size={14} /></a>}{USE_LOCAL_API && <small className="table-sub">D?s local server provides source metadata but no document previews.</small>}{USE_MOCKS && !USE_LOCAL_API && <small className="table-sub">Seed previews are fictional sample documents; uploaded previews show your file with simulated extracted fields.</small>}</section></div>; }

const DONE_STATUSES = ['processed', 'completed', 'ready'];
// No payout statement for the month yet: one thing to do (upload it), not one flag per revenue line.
const statementMissing = (r: Reconciliation) => r.lines.length > 0 && r.actual === 0 && r.lines.every(l => !l.docId && !l.actual);
const NEEDS_ATTENTION = ['needs_review', 'pending_review', 'failed', 'error', 'uploaded', 'extracting', 'processing'];
// Bill statuses that mean the document's review is over; the document then shows the bill's status.
const BILL_DECIDED = ['pending_approval', 'pending_docs', 'approved', 'scheduled', 'rejected'];
function withBillStatus(documents: Document[], bills: Bill[]): Document[] {
  return documents.map(doc => {
    const id = doc.id || (doc as Document & { documentId?: string }).documentId;
    const bill = bills.find(b => (b.docId && b.docId === id) || (doc.billId && b.id === doc.billId));
    if (!bill || !BILL_DECIDED.includes(bill.status)) return doc;
    return { ...doc, status: bill.status, vendorName: doc.vendorName || bill.vendor };
  });
}
const STATUS_NOTES: Record<string, string> = { needs_review: 'Couldn’t read this one confidently. Take a look.', uploaded: 'Uploaded. Reading starts in a moment.', extracting: 'Reading the document…', failed: 'Processing failed. Try uploading it again.', error: 'Processing failed. Try uploading it again.' };
function Intake({ documents, bills, openDoc, openBill }: { documents: Document[]; bills: Bill[]; openDoc: (id: string) => void; openBill: (id: string) => void }) {
  const reviewBills = bills.filter(b => b.status === 'pending_review');
  const reviewDocIds = new Set(reviewBills.map(b => b.docId));
  const waiting = documents.filter(d => !DONE_STATUSES.includes(d.status) && !reviewDocIds.has(d.id));
  const cutoff = Date.now() - 14 * 864e5;
  const recent = documents.filter(d => Date.parse(d.createdAt) >= cutoff && DONE_STATUSES.includes(d.status));
  const count = reviewBills.length + waiting.length;
  return <><section className="panel"><div className="panel-heading"><div><h2>Needs your attention <span className="muted">({count})</span></h2><p>Uploads the AI couldn’t finish on its own.</p></div></div>{count ? <div className="table-scroll"><table><thead><tr><th>Item</th><th>What’s needed</th><th>Status</th><th></th></tr></thead><tbody>
    {reviewBills.map(b => <tr key={b.id}><td><strong>{b.vendor || 'Unknown vendor'}</strong><small className="table-sub">{money(b.amount)}{b.invoiceNumber ? ` · ${b.invoiceNumber}` : ''}</small></td><td>Confirm the extracted fields before the bill goes through your rules.</td><td><Pill status={b.status} /></td><td><Button variant="outline" onClick={() => openBill(b.id)}>Review fields</Button></td></tr>)}
    {waiting.map(d => <tr key={d.id}><td><button className="document-link" onClick={() => openDoc(d.id)}><FileText size={17} />{d.filename}</button></td><td>{STATUS_NOTES[d.status] ?? 'In progress.'}</td><td><Pill status={d.status} /></td><td /></tr>)}
  </tbody></table></div> : <Empty text="Nothing waiting on you. New uploads show up here while they’re being read." />}</section>
  <DocumentTable documents={recent} openDoc={openDoc} title="Processed in the last 2 weeks" emptyText="No uploads processed in the last two weeks." />
  <p className="muted inbox-footnote">Older documents live in the <Link href="/library">Library</Link>.</p></>;
}
// Expense categories and their sub-accounts (backend/src/shared/coa.py). Bills are coded to the most specific one.
const EXPENSE_CHART: [string, string, [string, string][]][] = [
  ['6100', 'Staff and payroll', [['6110', 'Salaries and wages'], ['6120', 'Payroll taxes'], ['6130', 'Benefits']]],
  ['6200', 'Rent and occupancy', [['6210', 'Office rent'], ['6220', 'Utilities']]],
  ['6300', 'Technology', [['6310', 'Software subscriptions'], ['6320', 'Research and market data'], ['6330', 'Hardware and devices']]],
  ['6400', 'LPL platform fees', [['6410', 'Platform and admin fees'], ['6420', 'Technology and data fees']]],
  ['6500', 'Marketing', [['6510', 'Client events'], ['6520', 'Advertising and digital'], ['6530', 'Seminars and sponsorships']]],
  ['6600', 'Compliance and licensing', [['6610', 'Licensing and registration'], ['6620', 'E&O insurance'], ['6630', 'Compliance consultants']]],
  ['6700', 'Travel and entertainment', [['6710', 'Airfare'], ['6720', 'Car rides'], ['6730', 'Ground transportation'], ['6740', 'Parking'], ['6750', 'Lodging'], ['6760', 'Meals and entertainment']]],
  ['6900', 'Other expenses', [['6910', 'Office supplies'], ['6920', 'Bank and card fees']]],
];
const EXPENSE_ACCOUNTS: [string, string][] = EXPENSE_CHART.flatMap(([code, name, subs]) => [[code, name] as [string, string], ...subs]);
function BillDrawer({ bill, role, userId, busy: deciding, onDecide, onClose, onConfirmed, notify, openDoc }: { bill: BillDetail; role: Role; userId: string; busy: boolean; onDecide: (decision: 'approve' | 'reject', comment: string, changes?: BillApprovalChanges) => void; onClose: () => void; onConfirmed: () => void; notify: (text: string) => void; openDoc: (id: string) => void }) {
  const [busy, setBusy] = useState(false); const [comment, setComment] = useState(''); const [mode, setMode] = useState<'approve' | 'reject' | 'sendback'>('approve');
  const [doc, setDoc] = useState<Document>(); const [docError, setDocError] = useState(false);
  useEffect(() => { if (!bill.docId) return; let active = true; api.document(bill.docId).then(d => { if (active) setDoc(d); }).catch(() => { if (active) setDocError(true); }); return () => { active = false; }; }, [bill.docId]);
  const gl = bill.glAccount.split(' ')[0];
  const [category, setCategory] = useState(EXPENSE_ACCOUNTS.some(([code]) => code === gl) ? gl : '6900');
  const [invoiceNumber, setInvoiceNumber] = useState(bill.invoiceNumber ?? ''); const [dueDate, setDueDate] = useState(bill.dueDate ?? '');
  const awaiting = bill.status === 'pending_approval';
  const review = bill.status === 'pending_review';
  // Segregation of duties: whoever uploaded a bill can't approve it (the API refuses too).
  const ownUpload = Boolean(userId && bill.createdBy && bill.createdBy === userId);
  const approvers = approverNames(bill);
  const canDecide = awaiting && canApprove(bill, role, userId);
  const docsMissing = bill.ruleHits.some(h => h.toLowerCase().includes('missing'));
  const changes: BillApprovalChanges = { ...(category !== gl ? { glAccount: category } : {}), ...(invoiceNumber.trim() !== (bill.invoiceNumber ?? '') ? { invoiceNumber: invoiceNumber.trim() } : {}), ...(dueDate && dueDate !== (bill.dueDate ?? '') ? { dueDate } : {}) };
  const changed = Object.keys(changes).length > 0;
  const confirm = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault(); const form = new FormData(e.currentTarget); const amount = Number(String(form.get('amount')).replace(/[$,]/g, ''));
    if (!(amount > 0)) { notify('Enter the bill amount, like 1850.00.'); return; }
    const fields: BillReview = { amount, vendorName: String(form.get('vendorName')).trim(), glAccount: category, dueDate: dueDate || undefined, invoiceNumber: invoiceNumber.trim() || undefined };
    if (!fields.vendorName) { notify('Enter the vendor name.'); return; }
    setBusy(true); try { await api.confirmBill(bill.id, fields); notify('Fields confirmed. The bill is now running through your rules.'); onConfirmed(); } catch (err) { notify(message(err)); } finally { setBusy(false); }
  };
  const categoryPicker = <select name="glAccount" value={category} onChange={e => setCategory(e.target.value)}>{EXPENSE_CHART.map(([code, name, subs]) => <optgroup key={code} label={`${code} · ${name}`}><option value={code}>{code} · {name} (general)</option>{subs.map(([sub, subName]) => <option key={sub} value={sub}>{sub} · {subName}</option>)}</optgroup>)}</select>;
  const heading = review ? 'Review the extracted fields' : canDecide ? 'Waiting for your approval' : awaiting ? `Pending ${approvers} approval` : label(bill.status);
  return <div className="modal-backdrop" onClick={onClose}><section className="document-modal bill-drawer" role="dialog" aria-modal="true" aria-label="Bill review" onClick={e => e.stopPropagation()}>
    <div className="modal-title"><div><strong>{bill.vendor || 'Unknown vendor'} · {cents(bill.amount)}</strong><div className="document-badges"><Pill status={bill.status} />{bill.invoiceNumber && <span className="muted">Invoice {bill.invoiceNumber}</span>}</div></div><button autoFocus aria-label="Close bill" onClick={onClose}><X size={21} /></button></div>
    <div className="review-layout">
      <div className="review-preview">{doc?.viewUrl ? (doc.viewUrl.startsWith('blob:') && /\.(png|jpe?g)$/i.test(doc.filename) ? <img src={doc.viewUrl} alt={doc.filename} /> : <iframe title={`Invoice from ${bill.vendor}`} src={doc.viewUrl} />) : <Empty text={!bill.docId ? 'No document attached to this bill.' : docError ? 'Couldn’t load the invoice preview.' : 'Loading the invoice…'} />}{bill.docId && <button className="document-link review-open" onClick={() => openDoc(bill.docId!)}>Open full document <ArrowUpRight size={13} /></button>}</div>
      <div className="review-side">
        <h2>{heading}</h2>
        {bill.ruleHits.length > 0 && <div className="review-why"><span className="muted">Why it’s here</span>{bill.ruleHits.map(hit => <small className="rule-hit" key={hit}>{hit}</small>)}</div>}
        {review && canReviewDocuments(role) ? <form className="review-fields" onSubmit={confirm}>
          <p className="muted">The AI wasn’t confident about this one. Check each field against the invoice, fix anything wrong, then confirm.</p>
          <label>Vendor<input name="vendorName" defaultValue={bill.vendor} required maxLength={120} /></label>
          <label>Amount ($)<input name="amount" inputMode="decimal" defaultValue={bill.amount ? String(bill.amount) : ''} required /></label>
          <label>Category{categoryPicker}</label>
          <label>Invoice number<input value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} maxLength={60} /></label>
          <label>Due date<input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} /></label>
          <Button disabled={busy}><Check size={15} />{busy ? 'Confirming…' : 'Confirm fields'}</Button>
        </form> : <div className="review-fields">
          {review && <p className="muted">Only Owner or Ops can verify extracted bill fields. This bill is waiting for operations review.</p>}
          <div className="locked-field"><span>Vendor</span><strong>{bill.vendor || '—'}</strong></div>
          <div className="locked-field"><span>Amount</span><strong>{cents(bill.amount)}</strong></div>
          {canDecide ? <>
            <label>Category{categoryPicker}{bill.glAccountReason && <small className="table-sub">{bill.glAccountReason}</small>}</label>
            <label>Invoice number<input value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} maxLength={60} /></label>
            <label>Due date<input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} /></label>
            <label>{mode === 'approve' ? 'Comment (optional)' : mode === 'reject' ? 'Reason for rejecting (required)' : 'What needs fixing? (required)'}<textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} maxLength={500} placeholder={mode === 'approve' ? 'e.g. Approved for the Q4 CRM renewal' : mode === 'reject' ? 'e.g. Duplicate of last month’s invoice' : 'e.g. Amount should be $1,580, not $1,850'} /></label>
            {docsMissing && <p className="text-red">This vendor is still missing a W-9 or void check. Approval unlocks once those arrive.</p>}
            {mode === 'approve' ? <>
              <div className="decision-buttons"><Button disabled={deciding || docsMissing} onClick={() => onDecide('approve', comment, changed ? changes : undefined)}><Check size={15} />{deciding ? 'Approving…' : `Approve ${cents(bill.amount)}${changed ? ' with changes' : ''}`}</Button><Button variant="outline" disabled={deciding} onClick={() => setMode('reject')}>Reject…</Button></div>
              <p className="sendback">Amount or vendor wrong? <button className="document-link" disabled={deciding} onClick={() => setMode('sendback')}>Send back for review</button></p>
            </> : <div className="decision-buttons"><Button variant="destructive" disabled={deciding || !comment.trim()} onClick={() => onDecide('reject', mode === 'sendback' ? `Sent back for review: ${comment.trim()}` : comment)}>{deciding ? 'Sending…' : mode === 'sendback' ? 'Send back' : 'Confirm reject'}</Button><Button variant="outline" disabled={deciding} onClick={() => setMode('approve')}>Cancel</Button></div>}
            {mode === 'sendback' && <small className="table-sub">This rejects the bill with your note, so whoever submitted it can correct the amount or vendor and re-upload.</small>}
          </> : <>
            <div className="locked-field"><span>Category</span><strong>{bill.glAccount || '—'}</strong></div>
            <div className="locked-field"><span>Due</span><strong>{bill.dueDate || '—'}</strong></div>
            {bill.payment?.scheduledFor && <div className="locked-field"><span>Payment</span><strong>{bill.payment.method} on {bill.payment.scheduledFor}{bill.payment.confirmation ? ` · ${bill.payment.confirmation}` : ''}</strong></div>}
            {bill.rejectionReason && <div className="locked-field"><span>Rejected because</span><strong>{bill.rejectionReason}</strong></div>}
            {awaiting && <p className="muted">{ownUpload ? `You uploaded this bill, so someone else has to approve it (segregation of duties). It's waiting for ${approvers} approval.` : `You're signed in as ${label(role)}. Only ${approvers}${approvers === 'Owner' ? '' : ' or the owner'} can approve this bill.`}</p>}
            {bill.status === 'pending_docs' && <p className="muted">On hold until the vendor’s W-9 and void check are uploaded. It releases automatically when they arrive.</p>}
          </>}
        </div>}
      </div>
    </div>
    <h3 className="audit-heading">History</h3>{bill.audit.length ? <ol className="audit-trail">{bill.audit.map((a, i) => <li key={i}><div><strong>{label(a.action)}</strong> <span className="muted">by {a.actor}</span></div><small className="muted">{new Date(a.at).toLocaleString()}</small>{a.detail && <p>{a.detail}</p>}</li>)}</ol> : <p className="muted">No history recorded yet.</p>}
  </section></div>;
}
