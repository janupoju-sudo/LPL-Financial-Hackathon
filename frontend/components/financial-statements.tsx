import * as React from 'react';
import type { Financials } from '@/lib/types';
import { money } from '@/lib/format';

type Row = { name: string; amount: number; previous?: number; children?: Row[] };
type Section = { title: string; rows: Row[]; total?: Row };

// The statement of shareholders' equity is derived from the other three, so it always ties out:
// equity only moves through net income and owner contributions/distributions (financing cash flows),
// which makes beginning equity = ending equity (balance sheet) - net income - owner flows.
function equitySections(data: Financials): { sections: Section[]; note: string } {
  const netIncome = data.pnl.operatingIncome;
  const ownerFlows = data.cashFlow.financing.map(r => ({ name: r.label, amount: r.amount }));
  const ownerTotal = data.cashFlow.netFinancing;
  const ending = data.balanceSheet.totalEquity;
  const beginning = ending - netIncome - ownerTotal;
  return {
    note: `For ${data.pnl.period} · ends ${data.balanceSheet.asOf}`,
    sections: [
      { title: 'Beginning of period', rows: [], total: { name: "Beginning shareholders' equity", amount: beginning } },
      { title: 'Changes during the period', rows: [{ name: 'Net income', amount: netIncome }, ...(ownerFlows.length ? ownerFlows : [{ name: 'Owner contributions and distributions', amount: 0 }])], total: { name: 'Net change in equity', amount: netIncome + ownerTotal } },
      { title: 'End of period', rows: [], total: { name: "Ending shareholders' equity", amount: ending } },
    ],
  };
}

// Change vs the previous period, shown only when it's meaningful (both periods have activity).
function Change({ row, period }: { row: Row; period?: string }) {
  if (!row.previous || !row.amount) return null;
  const pct = (row.amount - row.previous) / row.previous * 100;
  if (Math.abs(pct) < 1) return null;
  return <span className={`change ${pct > 0 ? 'up' : 'down'}`} title={`${money(row.previous)} in ${period ?? 'the previous period'}`}>{pct > 0 ? '+' : ''}{pct.toFixed(0)}%</span>;
}

function StatementRow({ row, period }: { row: Row; period?: string }) {
  const [open, setOpen] = React.useState(false);
  const kids = row.children ?? [];
  if (!kids.length) return <div className="statement-row"><span>{row.name}<Change row={row} period={period} /></span><span>{money(row.amount)}</span></div>;
  return <>
    <button type="button" className="statement-row expandable" aria-expanded={open} onClick={() => setOpen(!open)}><span><i className="caret" aria-hidden="true">{open ? '▾' : '▸'}</i>{row.name}<Change row={row} period={period} /></span><span>{money(row.amount)}</span></button>
    {open && kids.map((child, i) => <div className="statement-row sub" key={`${child.name}-${i}`}><span>{child.name}<Change row={child} period={period} /></span><span>{money(child.amount)}</span></div>)}
  </>;
}

export function FinancialStatement({ data, tab }: { data: Financials; tab: string }) {
  let sections: Section[]; let note: string;
  const previous = data.kpis.previous?.period;
  if (tab === 'Income statement') {
    note = `For ${data.pnl.period}`;
    sections = [
      { title: 'Revenue', rows: data.pnl.revenue, total: { name: 'Total revenue', amount: data.pnl.totalRevenue } },
      { title: 'Operating expenses', rows: data.pnl.expenses, total: { name: 'Total expenses', amount: data.pnl.totalExpenses } },
      { title: 'Net income', rows: [], total: { name: 'Net income', amount: data.pnl.operatingIncome } },
    ];
  } else if (tab === "Shareholders' equity") {
    ({ sections, note } = equitySections(data));
  } else if (tab === 'Balance sheet') {
    note = `As of ${data.balanceSheet.asOf}`;
    sections = [
      { title: 'Assets', rows: data.balanceSheet.assets, total: { name: 'Total assets', amount: data.balanceSheet.totalAssets } },
      { title: 'Liabilities', rows: data.balanceSheet.liabilities, total: { name: 'Total liabilities', amount: data.balanceSheet.totalLiabilities } },
      { title: "Shareholders' equity", rows: data.balanceSheet.equity, total: { name: "Total shareholders' equity", amount: data.balanceSheet.totalEquity } },
      { title: '', rows: [], total: { name: "Total liabilities and shareholders' equity", amount: data.balanceSheet.totalLiabilities + data.balanceSheet.totalEquity } },
    ];
  } else {
    note = `For ${data.cashFlow.period}`;
    sections = [
      { title: 'Operating activities', rows: data.cashFlow.operating.map(r => ({ name: r.label, amount: r.amount })), total: { name: 'Net cash from operating activities', amount: data.cashFlow.netOperating } },
      { title: 'Financing activities', rows: data.cashFlow.financing.map(r => ({ name: r.label, amount: r.amount })), total: { name: 'Net cash from financing activities', amount: data.cashFlow.netFinancing } },
      { title: 'Cash', rows: [{ name: 'Beginning cash', amount: data.cashFlow.beginningCash }, { name: 'Net change in cash', amount: data.cashFlow.netChange }], total: { name: 'Ending cash', amount: data.cashFlow.endingCash } },
    ];
  }
  return <div className="statement"><p className="muted">{note}</p>{sections.map((section, i) => <section className="statement-section" key={`${section.title}-${i}`}>{section.title && section.rows.length > 0 && <h3>{section.title}</h3>}{section.rows.map((row, index) => <StatementRow key={`${row.name}-${index}`} row={row} period={previous} />)}{section.total && <div className="statement-row statement-total"><strong>{section.total.name}</strong><strong>{money(section.total.amount)}</strong></div>}</section>)}</div>;
}
