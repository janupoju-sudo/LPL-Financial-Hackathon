import type { AccountLine, AuditEvent, Bill, BillDetail, BillStatus, Document, Financials, Reconciliation, Rule, Vendor } from './types';

/** Current main also accepts the earlier frontend shape. Normalize at the boundary;
 * ratio units follow the statement shape, never the magnitude of a KPI value. */
export interface LegacyFinancials {
  period: string;
  pnl: { revenue: number; expenses: number; netIncome: number; revenueLines: AccountLine[]; expenseLines: AccountLine[] };
  balanceSheet: { asOf: string; assets: number; liabilities: number; equity: number; assetLines: AccountLine[]; liabilityLines: AccountLine[]; equityLines: AccountLine[] };
  cashFlow: { operating: number; financing: number; net: number; beginningCash: number; endingCash: number; operatingLines: { label: string; amount: number }[]; financingLines: { label: string; amount: number }[] };
  kpis: { margin: number | null; recurringPct: number | null; revPerClient: number | null; expenseRatios: { account: string; name: string; ratio: number | null }[]; previous: { period: string; revenue: number; margin: number | null; recurringPct: number | null } };
  valuation: Financials['valuation'];
}
export function normalizeFinancials(response: Financials | LegacyFinancials): Financials {
  if (Array.isArray(response.pnl.revenue)) return response as Financials;
  const data = response as LegacyFinancials;
  const ratio = (percent: number | null) => percent === null ? null : percent / 100;
  return {
    period: data.period,
    pnl: { period: data.period, revenue: data.pnl.revenueLines, totalRevenue: data.pnl.revenue, expenses: data.pnl.expenseLines, totalExpenses: data.pnl.expenses, operatingIncome: data.pnl.netIncome },
    balanceSheet: { asOf: data.balanceSheet.asOf, assets: data.balanceSheet.assetLines, totalAssets: data.balanceSheet.assets, liabilities: data.balanceSheet.liabilityLines, totalLiabilities: data.balanceSheet.liabilities, equity: data.balanceSheet.equityLines, totalEquity: data.balanceSheet.equity },
    cashFlow: { period: data.period, beginningCash: data.cashFlow.beginningCash, operating: data.cashFlow.operatingLines, netOperating: data.cashFlow.operating, financing: data.cashFlow.financingLines, netFinancing: data.cashFlow.financing, netChange: data.cashFlow.net, endingCash: data.cashFlow.endingCash },
    kpis: { margin: ratio(data.kpis.margin), recurringPct: ratio(data.kpis.recurringPct), revPerClient: data.kpis.revPerClient, expenseRatios: data.kpis.expenseRatios.map(row => ({ ...row, ratio: ratio(row.ratio) })), previous: { period: data.kpis.previous.period, totalRevenue: data.kpis.previous.revenue, margin: ratio(data.kpis.previous.margin), recurringPct: ratio(data.kpis.previous.recurringPct) } },
    valuation: data.valuation
  };
}
type MainReconciliation = Omit<Reconciliation, 'flags'> & { flags: (Omit<Reconciliation['flags'][number], 'message'> & { reason: string; message?: string })[] };
export function normalizeReconciliation(response: Reconciliation | MainReconciliation): Reconciliation {
  return { ...response, flags: response.flags.map(flag => ({ lineId: flag.lineId, status: flag.status, severity: flag.severity, message: flag.message ?? ('reason' in flag ? flag.reason : '') })) };
}

/* C's live API (backend/README.md) names ids per entity (documentId, billId, vendorId, ruleId),
 * sends vendorName/documentId on bills, structured ruleHits, and calls the docs-hold action "hold".
 * Map those to the frontend types at the boundary; mock fixtures already use the frontend shape. */
type Hit = string | { ruleId?: string; name?: string; action?: string; reason?: string };
export type ApiDocument = Omit<Document, 'id'> & { documentId: string; id?: string };
export type ApiBill = Partial<Omit<Bill, 'ruleHits'>> & { billId: string; documentId?: string; vendorName?: string; glAccountName?: string; ruleHits?: Hit[]; audit?: AuditEvent[]; payment?: BillDetail['payment']; rejectionReason?: string; invoiceDate?: string };
export type ApiVendor = Omit<Vendor, 'id'> & { vendorId: string; id?: string };
export type ApiRule = Omit<Rule, 'id' | 'action'> & { ruleId: string; id?: string; action: Rule['action'] | 'hold' };

export const normalizeDocument = ({ documentId, ...doc }: ApiDocument): Document => ({ ...doc, id: doc.id ?? documentId });
export function normalizeBill(bill: ApiBill): Bill {
  const gl = bill.glAccount ?? '';
  return {
    id: bill.id ?? bill.billId,
    docId: bill.docId ?? bill.documentId,
    vendor: bill.vendor ?? bill.vendorName ?? '',
    vendorId: bill.vendorId,
    amount: Number(bill.amount ?? 0),
    dueDate: bill.dueDate ?? '',
    glAccount: bill.glAccountName && gl && !gl.includes('·') ? `${gl} · ${bill.glAccountName}` : gl,
    status: bill.status as BillStatus,
    ruleHits: (bill.ruleHits ?? []).map(hit => typeof hit === 'string' ? hit : hit.reason ?? hit.name ?? ''),
    ...(bill.invoiceNumber ? { invoiceNumber: bill.invoiceNumber } : {}),
    ...(bill.requiredApprovers ? { requiredApprovers: bill.requiredApprovers } : {}),
    ...(bill.createdAt ? { createdAt: bill.createdAt } : {}),
  };
}
export const normalizeBillDetail = (bill: ApiBill): BillDetail => ({
  ...normalizeBill(bill), audit: bill.audit ?? [], payment: bill.payment, rejectionReason: bill.rejectionReason, invoiceDate: bill.invoiceDate,
});
export const normalizeVendor = ({ vendorId, ...vendor }: ApiVendor): Vendor => ({ ...vendor, id: vendor.id ?? vendorId });
export const normalizeRule = ({ ruleId, action, ...rule }: ApiRule): Rule => ({ ...rule, id: rule.id ?? ruleId, action: action === 'hold' ? 'require_docs' : action });
export const toApiRule = (rule: Omit<Rule, 'id'>) => ({ ...rule, action: rule.action === 'require_docs' ? 'hold' : rule.action });
