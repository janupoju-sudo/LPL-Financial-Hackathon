import documentsFixture from '@/mocks/documents.json';
import billsFixture from '@/mocks/bills.json';
import vendorsFixture from '@/mocks/vendors.json';
import rulesFixture from '@/mocks/rules.json';
import financialsFixture from '@/mocks/financials.json';
import reconciliationFixture from '@/mocks/reconciliation.json';
import askFixture from '@/mocks/ask.json';
import type { Answer, Bill, BillDetail, BillReview, CardTransaction, Document, ExportResult, Financials, Reconciliation, Role, Rule, Vendor } from './types';
import { normalizeBill, normalizeBillDetail, normalizeDocument, normalizeFinancials, normalizeReconciliation, normalizeRule, normalizeVendor, toApiRule, type ApiBill, type ApiDocument, type ApiRule, type ApiVendor, type LegacyFinancials } from './contracts';
import { localDocuments } from './local-documents';
import { validateLocalApi } from './local-mode';

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS !== 'false';
export const USE_LOCAL_API = process.env.NEXT_PUBLIC_LOCAL_API === 'true';
const MOCK_D = USE_MOCKS && !USE_LOCAL_API;
const baseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
const clone = <T,>(value: T): T => structuredClone(value);
const seedDocuments = documentsFixture as unknown as Document[];
let documents = clone(seedDocuments);
let bills = clone(billsFixture) as Bill[];
let vendors = clone(vendorsFixture) as Vendor[];
let rules = clone(rulesFixture) as Rule[];
const listeners = new Set<() => void>();
export function subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; }
function changed() { listeners.forEach(listener => listener()); }
async function request<T>(path: string, body?: unknown): Promise<T> {
  if (!baseUrl) throw new Error('Set NEXT_PUBLIC_API_URL to connect to the backend.');
  const headers: Record<string, string> = body === undefined ? {} : { 'Content-Type': 'application/json' };
  if (USE_LOCAL_API) validateLocalApi(baseUrl);
  else {
    const { fetchAuthSession } = await import('aws-amplify/auth');
    const token = (await fetchAuthSession()).tokens?.idToken?.toString();
    if (!token) throw new Error('Please sign in again.');
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${baseUrl}${path}`, { method: body === undefined ? 'GET' : 'POST', headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw new Error(`Request failed (${response.status}): ${(await response.text()).slice(0, 200)}`);
  return response.json() as Promise<T>;
}
export const api = {
  documents: () => USE_LOCAL_API ? Promise.resolve(clone(localDocuments)) : USE_MOCKS ? Promise.resolve(clone(documents)) : request<ApiDocument[]>('/documents').then(list => list.map(normalizeDocument)),
  document: (id: string) => { if (!USE_MOCKS && !USE_LOCAL_API) return request<ApiDocument>(`/documents/${encodeURIComponent(id)}`).then(normalizeDocument); const doc = (USE_LOCAL_API ? localDocuments : documents).find(d => d.id === id); return doc ? Promise.resolve(clone(doc)) : Promise.reject(new Error(USE_LOCAL_API ? `Source ${id} is not available in D's local document metadata. The local server has no document-preview endpoint.` : 'Document not found')); },
  bills: () => USE_LOCAL_API ? Promise.resolve([] as Bill[]) : USE_MOCKS ? Promise.resolve(clone(bills)) : request<ApiBill[]>('/bills').then(list => list.map(normalizeBill)),
  vendors: () => USE_LOCAL_API ? Promise.resolve([] as Vendor[]) : USE_MOCKS ? Promise.resolve(clone(vendors)) : request<ApiVendor[]>('/vendors').then(list => list.map(normalizeVendor)),
  bill: (id: string): Promise<BillDetail> => { if (!USE_MOCKS && !USE_LOCAL_API) return request<ApiBill>(`/bills/${encodeURIComponent(id)}`).then(normalizeBillDetail); const bill = bills.find(b => b.id === id); return bill ? Promise.resolve({ ...clone(bill), audit: [] }) : Promise.reject(new Error('Bill not found')); },
  async confirmBill(id: string, review: BillReview) {
    if (USE_MOCKS || USE_LOCAL_API) throw new Error('Reviewing bills needs the live backend.');
    const result = await request<{ billId: string; status: string }>(`/bills/${encodeURIComponent(id)}/confirm`, review); changed(); return result;
  },
  transactions: (): Promise<CardTransaction[]> => USE_MOCKS || USE_LOCAL_API ? Promise.resolve([]) : request<CardTransaction[]>('/transactions'),
  rules: () => USE_LOCAL_API ? Promise.resolve([] as Rule[]) : USE_MOCKS ? Promise.resolve(clone(rules)) : request<ApiRule[]>('/rules').then(list => list.map(normalizeRule)),
  financials: (period: string) => MOCK_D ? Promise.resolve(mockFinancials()) : request<Financials | LegacyFinancials>(`/financials?period=${encodeURIComponent(period)}`).then(normalizeFinancials),
  reconciliation: (period: string) => MOCK_D ? Promise.resolve(clone(reconciliationFixture)) : request<Parameters<typeof normalizeReconciliation>[0]>(`/revenue/reconciliation?period=${encodeURIComponent(period)}`).then(normalizeReconciliation),
  ask: (question: string) => MOCK_D ? Promise.resolve({ ...clone(askFixture), answer: `Demo response (sample context): ${askFixture.answer}` } as Answer) : request<Answer>('/ask', { question }),
  async decision(id: string, decision: 'approve' | 'reject', comment: string, role: Role) {
    if (USE_LOCAL_API) throw new Error('D’s local server does not support bill decisions.');
    if (!USE_MOCKS) { const result = await request<{ billId: string; status: string }>(`/bills/${encodeURIComponent(id)}/decision`, { decision, comment }); changed(); return { id: result.billId ?? id, status: result.status }; }
    const bill = bills.find(b => b.id === id);
    if (!bill || bill.status !== 'pending_approval') throw new Error('This bill is not awaiting approval.');
    if (role !== 'partner' && role !== 'owner') throw new Error('Switch to Owner or Partner to make a decision.');
    if (decision === 'approve' && bill.ruleHits.some(hit => hit.includes('missing'))) throw new Error('Upload the vendor W-9 and void check before approval.');
    bill.status = decision === 'approve' ? 'scheduled' : 'rejected'; changed(); return { id, status: bill.status };
  },
  async createRule(input: Omit<Rule, 'id'>) { if (USE_LOCAL_API) throw new Error('D’s local server does not support rules.'); if (!USE_MOCKS) { await request<ApiRule>('/rules', toApiRule(input)); changed(); return api.rules(); } rules.push({ ...input, id: crypto.randomUUID() }); changed(); return clone(rules); },
  async upload(file: File, onProgress: (status: string) => void, signal?: AbortSignal): Promise<Document> {
    if (USE_LOCAL_API) throw new Error('D’s local server does not support uploads.');
    if (file.size > 20 * 1024 * 1024) throw new Error('Files must be smaller than 20 MB.');
    if (!['application/pdf', 'image/png', 'image/jpeg'].includes(file.type)) throw new Error('Choose a PDF, PNG, or JPG document.');
    onProgress('Uploading');
    if (!USE_MOCKS) {
      const { documentId, uploadUrl } = await request<{ documentId: string; uploadUrl: string }>('/documents/upload-url', { filename: file.name, contentType: file.type });
      const response = await fetch(uploadUrl, { method: 'PUT', headers: { 'Content-Type': file.type }, body: file, signal });
      if (!response.ok) throw new Error('The document upload failed. Please try again.');
      for (let attempt = 0; attempt < 60; attempt++) {
        signal?.throwIfAborted();
        onProgress('Extracting fields');
        const doc = await api.document(documentId);
        if (['failed', 'error'].includes(doc.status)) throw new Error('Processing failed. Please try another document.');
        if (['processed', 'completed', 'ready', 'needs_review', 'pending_review', 'pending_approval'].includes(doc.status)) { changed(); return doc; }
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      throw new Error('Processing is taking longer than expected. Check the Library for updates.');
    }
    // Mock extraction is explicitly simulated; it never claims to parse the uploaded file.
    await new Promise(resolve => setTimeout(resolve, 700)); signal?.throwIfAborted(); onProgress('Demo extraction');
    const name = file.name.toLowerCase();
    const type = name.includes('w9') || name.includes('w-9') ? 'w9' : name.includes('check') ? 'void_check' : name.includes('payout') ? 'payout_statement' : name.includes('receipt') ? 'receipt' : 'invoice';
    const template = seedDocuments[type === 'payout_statement' ? 3 : type === 'receipt' ? 2 : 0];
    const doc: Document = { ...clone(template), id: crypto.randomUUID(), type, filename: file.name, createdAt: new Date().toISOString().slice(0, 10), viewUrl: URL.createObjectURL(file), billId: undefined };
    if (type === 'w9' || type === 'void_check') {
      const vendor = vendors.find(v => v.id === 'v2')!;
      if (type === 'w9') vendor.hasW9 = true; else vendor.hasVoidCheck = true;
      doc.vendorName = vendor.name; doc.amount = 0; doc.extracted = { vendor: vendor.name, documentType: type, demo: 'Assigned to Brightline Marketing for this demo' };
      if (vendor.hasW9 && vendor.hasVoidCheck) bills.filter(b => b.vendorId === vendor.id).forEach(b => { b.ruleHits = b.ruleHits.filter(hit => !hit.includes('missing')); });
    } else if (type !== 'payout_statement') {
      doc.billId = crypto.randomUUID();
      bills.unshift({ id: doc.billId, docId: doc.id, vendorId: type === 'invoice' ? 'v1' : undefined, vendor: doc.vendorName, amount: doc.amount, dueDate: '2026-10-15', glAccount: String(doc.extracted.glAccount), status: (doc.confidence ?? 1) < .8 ? 'pending_review' : 'pending_approval', ruleHits: [(doc.confidence ?? 1) < .8 ? 'Extraction confidence below 80%; verify document fields' : 'Amount over $1,000 requires partner approval'] });
    }
    documents.unshift(doc); changed(); return clone(doc);
  },
  async export(period: string): Promise<ExportResult> {
    if (!MOCK_D) return request<ExportResult>('/export', { period });
    const { buildExport } = await import('./export');
    const result = await buildExport(documents, bills, mockFinancials(), period);
    return { downloadUrl: URL.createObjectURL(result.blob), ...result.summary };
  },
  async importTransactions(file: File) {
    if (USE_LOCAL_API) throw new Error('D’s local server does not support CSV import.');
    if (USE_MOCKS) throw new Error('CSV import requires the live /transactions/import endpoint.');
    const { fetchAuthSession } = await import('aws-amplify/auth');
    const token = (await fetchAuthSession()).tokens?.idToken?.toString();
    if (!baseUrl || !token) throw new Error('Sign in and configure the API first.');
    const response = await fetch(`${baseUrl}/transactions/import`, { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'text/csv' }, body: file });
    if (!response.ok) throw new Error('CSV import failed.'); changed();
    return response.json() as Promise<{ imported: number; categorized: number; matchedReceipts: number }>;
  }
};
function mockFinancials(): Financials {
  const data: Financials = clone(financialsFixture);
  const newExpense = bills.filter(b => b.status === 'scheduled' && b.id !== 'b4').reduce((sum, b) => sum + b.amount, 0);
  for (const bill of bills.filter(b => b.status === 'scheduled' && b.id !== 'b4')) {
    const account = bill.glAccount.slice(0, 4);
    let line = data.pnl.expenses.find(row => row.account === account);
    if (!line) { line = { account, name: bill.glAccount.split('·')[1]?.trim() ?? bill.glAccount, amount: 0 }; data.pnl.expenses.push(line); }
    line.amount += bill.amount;
  }
  data.pnl.totalExpenses += newExpense; data.pnl.operatingIncome -= newExpense;
  data.kpis.margin = data.pnl.totalRevenue ? data.pnl.operatingIncome / data.pnl.totalRevenue : null;
  data.kpis.expenseRatios = data.pnl.expenses.map(line => ({ account: line.account!, name: line.name, ratio: data.pnl.totalRevenue ? line.amount / data.pnl.totalRevenue : null }));
  data.balanceSheet.totalAssets -= newExpense; data.balanceSheet.totalEquity -= newExpense;
  data.balanceSheet.assets[0].amount -= newExpense; data.balanceSheet.equity[1].amount -= newExpense;
  data.cashFlow.operating[1].amount -= newExpense;
  data.cashFlow.netOperating -= newExpense; data.cashFlow.netChange -= newExpense; data.cashFlow.endingCash -= newExpense;
  return data;
}
