export type Role = 'owner' | 'partner' | 'ops' | 'lpl_bookkeeper';
export type DocumentType = 'invoice' | 'receipt' | 'void_check' | 'w9' | 'payout_statement';
export type BillStatus = 'pending_review' | 'processing' | 'pending_approval' | 'pending_docs' | 'approved' | 'rejected' | 'scheduled';
export interface Document { id: string; type: DocumentType; filename: string; status: string; vendorName: string; amount: number; createdAt: string; confidence?: number | null; extracted: Record<string, string | number>; viewUrl: string; billId?: string; }
export interface Bill { id: string; docId?: string; vendor: string; vendorId?: string; amount: number; dueDate: string; glAccount: string; glAccountReason?: string; status: BillStatus; ruleHits: string[]; invoiceNumber?: string; requiredApprovers?: string[]; createdAt?: string; }
export interface AuditEvent { at: string; actor: string; action: string; detail?: string; }
export interface BillDetail extends Bill { audit: AuditEvent[]; createdBy?: string; payment?: { method?: string; scheduledFor?: string; confirmation?: string; bankLast4?: string | null }; rejectionReason?: string; invoiceDate?: string; }
export interface BillReview { amount?: number; vendorName?: string; glAccount?: string; dueDate?: string; invoiceNumber?: string; }
export interface CardTransaction { txnId: string; date: string; description: string; amount: number; glAccount: string; glAccountName: string; categoryReason?: string | null; receiptDocumentId?: string | null; journalId?: string; }
export interface Vendor { id: string; name: string; defaultGlAccount: string; hasW9: boolean; hasVoidCheck: boolean; billCount: number; bankDetailReviewRequired?: boolean; possibleDuplicateVendorNames?: string[]; }
export interface RuleCondition { field?: string; op?: string; value?: string | number | boolean; all?: RuleCondition[]; any?: RuleCondition[]; not?: RuleCondition; }
export interface Rule { id: string; name: string; condition: RuleCondition; action: 'require_approval' | 'require_docs' | 'block'; approverRole?: Role; reason?: string; }
export interface AccountLine { account: string | null; name: string; amount: number; previous?: number; children?: AccountLine[]; }
export interface Financials {
  period: string;
  pnl: { period: string; revenue: AccountLine[]; totalRevenue: number; expenses: AccountLine[]; totalExpenses: number; operatingIncome: number };
  balanceSheet: { asOf: string; assets: AccountLine[]; totalAssets: number; liabilities: AccountLine[]; totalLiabilities: number; equity: AccountLine[]; totalEquity: number };
  cashFlow: { period: string; beginningCash: number; operating: { label: string; amount: number }[]; netOperating: number; financing: { label: string; amount: number }[]; netFinancing: number; netChange: number; endingCash: number };
  kpis: { margin: number | null; recurringPct: number | null; revPerClient: number | null; expenseRatios: { account: string; name: string; ratio: number | null }[]; previous: { period: string; totalRevenue: number; margin: number | null; recurringPct: number | null } };
  valuation: { low: number; mid: number; high: number; method: string; recurringRevenueTtm: number; multiples: { low: number; mid: number; high: number } };
  monthly?: { month: string; period: string; revenue: number; expenses: number }[];
}
export type ReconciliationStatus = 'ok' | 'short' | 'over' | 'missing' | 'unexpected';
export interface Reconciliation {
  period: string; expected: number; actual: number; variance: number;
  lines: { id: string; label: string; source: string; ref: string | null; expected: number; actual: number; variance: number; status: ReconciliationStatus; docId: string | null; reason?: string }[];
  flags: { lineId: string; status: ReconciliationStatus; severity: 'high' | 'medium' | 'low'; message: string }[];
}
export interface Answer { answer: string; citations: { documentId: string; label: string; snippet: string }[]; period: string; }
export interface ExportResult { downloadUrl: string; documents: number; ledgerLines: number; missing: string[]; }
