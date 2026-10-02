export type Role = 'owner' | 'partner' | 'ops' | 'lpl_bookkeeper';
export type DocumentType = 'invoice' | 'receipt' | 'void_check' | 'w9' | 'payout_statement';
export type BillStatus = 'pending_review' | 'pending_approval' | 'approved' | 'rejected' | 'scheduled';
export interface Document { id: string; type: DocumentType; filename: string; status: string; vendorName: string; amount: number; createdAt: string; confidence: number; extracted: Record<string, string | number>; viewUrl: string; billId?: string; }
export interface Bill { id: string; docId?: string; vendor: string; vendorId?: string; amount: number; dueDate: string; glAccount: string; status: BillStatus; ruleHits: string[]; }
export interface Vendor { id: string; name: string; defaultGlAccount: string; hasW9: boolean; hasVoidCheck: boolean; billCount: number; }
export interface Rule { id: string; name: string; condition: { field: string; op: string; value: string | number | boolean }; action: 'require_approval' | 'require_docs' | 'block'; approverRole: Role; }
export interface Financials { pnl: { revenue: number; expenses: number; netIncome: number; monthly: { month: string; revenue: number; expenses: number }[]; categories: { name: string; amount: number }[] }; balanceSheet: { assets: number; liabilities: number; equity: number }; cashFlow: { operating: number; investing: number; financing: number; net: number }; kpis: { margin: number; recurringPct: number; revPerClient: number }; valuation: { low: number; mid: number; high: number; method: string }; }
export interface Reconciliation { expected: number; actual: number; variance: number; lines: { id: string; source: string; label: string; expected: number; actual: number; variance: number; docId: string }[]; flags: { id: string; reason: string; docId: string }[]; }
export interface Answer { answer: string; citations: { documentId: string; label: string; snippet: string }[]; }
