import type { AccountLine, Financials, Reconciliation } from './types';

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
