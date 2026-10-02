import * as React from 'react';
import type { Financials } from '@/lib/types';
import { money } from '@/lib/format';

export function FinancialStatement({ data, tab }: { data: Financials; tab: string }) {
  const sections = tab === 'Balance sheet' ? [
    { title: 'Assets', rows: data.balanceSheet.assets, total: data.balanceSheet.totalAssets },
    { title: 'Liabilities', rows: data.balanceSheet.liabilities, total: data.balanceSheet.totalLiabilities },
    { title: 'Equity', rows: data.balanceSheet.equity, total: data.balanceSheet.totalEquity }
  ] : [
    { title: 'Operating activities', rows: data.cashFlow.operating.map(r => ({ name: r.label, amount: r.amount })), total: data.cashFlow.netOperating },
    { title: 'Financing activities', rows: data.cashFlow.financing.map(r => ({ name: r.label, amount: r.amount })), total: data.cashFlow.netFinancing }
  ];
  return <div className="statement"><p className="muted">{tab === 'Balance sheet' ? `As of ${data.balanceSheet.asOf}` : data.cashFlow.period}</p>{sections.map(section => <section className="statement-section" key={section.title}><h3>{section.title}</h3>{section.rows.map((row, index) => <div className="statement-row" key={`${row.name}-${index}`}><span>{row.name}</span><span>{money(row.amount)}</span></div>)}<div className="statement-row statement-total"><strong>Total {section.title.toLowerCase()}</strong><strong>{money(section.total)}</strong></div></section>)}{tab === 'Cash flow' && <section className="statement-section">{[{ name: 'Beginning cash', amount: data.cashFlow.beginningCash }, { name: 'Net change in cash', amount: data.cashFlow.netChange }, { name: 'Ending cash', amount: data.cashFlow.endingCash }].map(row => <div className="statement-row statement-total" key={row.name}><strong>{row.name}</strong><strong>{money(row.amount)}</strong></div>)}</section>}</div>;
}
