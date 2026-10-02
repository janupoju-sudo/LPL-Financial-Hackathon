import { test } from 'node:test';
import assert from 'node:assert/strict';
import { api } from './api';
import { zip } from './export';
import { percent } from './format';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { FinancialStatement } from '../components/financial-statements';
import { Revenue } from '../components/revenue-view';
import financialsFixture from '../mocks/financials.json';
import reconciliationFixture from '../mocks/reconciliation.json';
import type { Financials, Reconciliation } from './types';
import { normalizeFinancials, normalizeReconciliation, type LegacyFinancials } from './contracts';

test('approval enforces role, unblocks on vendor documents, and updates balanced financials', async () => {
  const before = await api.financials('2026-Q3');
  await assert.rejects(api.decision('b1', 'approve', '', 'ops'), /Switch/);
  await assert.rejects(api.decision('b2', 'approve', '', 'partner'), /W-9/);
  await api.upload(new File(['sample'], 'northstar-w9.pdf', { type: 'application/pdf' }), () => {});
  await assert.rejects(api.decision('b2', 'approve', '', 'partner'), /W-9/);
  await api.upload(new File(['sample'], 'northstar-void-check.pdf', { type: 'application/pdf' }), () => {});
  assert.equal((await api.decision('b2', 'approve', '', 'partner')).status, 'scheduled');
  assert.equal((await api.decision('b1', 'approve', '', 'partner')).status, 'scheduled');
  await assert.rejects(api.decision('b1', 'approve', '', 'partner'), /not awaiting/);
  const after = await api.financials('2026-Q3');
  assert.equal(after.pnl.totalExpenses - before.pnl.totalExpenses, 4300);
  assert.equal(before.pnl.operatingIncome - after.pnl.operatingIncome, 4300);
  assert.equal(after.balanceSheet.totalAssets, after.balanceSheet.totalEquity + after.balanceSheet.totalLiabilities);
  assert.equal(before.cashFlow.netChange - after.cashFlow.netChange, 4300);
  assert.ok(after.kpis.margin !== null && after.kpis.margin < 1);
  assert.equal(after.pnl.expenses.reduce((sum, row) => sum + row.amount, 0), after.pnl.totalExpenses);
  assert.equal(after.balanceSheet.assets.reduce((sum, row) => sum + row.amount, 0), after.balanceSheet.totalAssets);
});
test('D financial statements render account arrays and ratios without invalid numbers', () => {
  const data: Financials = financialsFixture;
  assert.equal(percent(.387), '38.7%');
  assert.equal(percent(.86), '86.0%');
  assert.equal(percent(0), '0.0%');
  assert.equal(percent(null), '—');
  for (const tab of ['Balance sheet', 'Cash flow']) {
    const html = renderToStaticMarkup(createElement(FinancialStatement, { data, tab }));
    assert.ok(html.includes('$482,000'));
    assert.ok(!html.includes('NaN'));
    assert.ok(!html.includes('[object Object]'));
  }
});
test('current-main percentage points convert by shape, including values below 1%', () => {
  const f = financialsFixture;
  const legacy: LegacyFinancials = {
    period: f.period,
    pnl: { revenue: f.pnl.totalRevenue, expenses: f.pnl.totalExpenses, netIncome: f.pnl.operatingIncome, revenueLines: f.pnl.revenue, expenseLines: f.pnl.expenses },
    balanceSheet: { asOf: f.balanceSheet.asOf, assets: f.balanceSheet.totalAssets, liabilities: f.balanceSheet.totalLiabilities, equity: f.balanceSheet.totalEquity, assetLines: f.balanceSheet.assets, liabilityLines: f.balanceSheet.liabilities, equityLines: f.balanceSheet.equity },
    cashFlow: { operating: f.cashFlow.netOperating, financing: f.cashFlow.netFinancing, net: f.cashFlow.netChange, beginningCash: f.cashFlow.beginningCash, endingCash: f.cashFlow.endingCash, operatingLines: f.cashFlow.operating, financingLines: f.cashFlow.financing },
    kpis: { margin: .5, recurringPct: 86, revPerClient: f.kpis.revPerClient, expenseRatios: [{ account: '6300', name: 'Technology', ratio: .5 }], previous: { period: '2026-Q2', revenue: 351100, margin: null, recurringPct: 85 } },
    valuation: f.valuation
  };
  const result = normalizeFinancials(legacy);
  assert.equal(percent(result.kpis.margin), '0.5%');
  assert.equal(result.kpis.expenseRatios[0].ratio, .005);
  assert.equal(result.kpis.recurringPct, .86);
  assert.equal(result.kpis.previous.margin, null);
  assert.equal(result.kpis.previous.totalRevenue, 351100);
  assert.strictEqual(normalizeFinancials(f), f);
  assert.deepEqual(result.pnl.revenue, f.pnl.revenue);
});
test('current-main reconciliation reason becomes the canonical flag message', () => {
  const data: Reconciliation = { ...reconciliationFixture, lines: [], flags: [] };
  const response = normalizeReconciliation({ ...data, flags: [{ lineId: 'rev3', status: 'short', severity: 'high', reason: 'Trail is $412 short.' }] });
  assert.equal(response.flags[0].message, 'Trail is $412 short.');
});
test('reconciliation uses line status and handles a missing payout with no source document', () => {
  const data: Reconciliation = { ...reconciliationFixture, lines: [{ id: 'missing-1', label: 'Unpaid advisory fee', source: 'advisory', ref: null, expected: 100, actual: 0, variance: -100, status: 'missing', docId: null }], flags: [{ lineId: 'missing-1', status: 'missing', severity: 'high', message: 'Unpaid advisory fee is missing.' }] };
  const html = renderToStaticMarkup(createElement(Revenue, { data, openDoc: () => { throw new Error('No source to open'); } }));
  assert.ok(html.includes('Unpaid advisory fee is missing.'));
  assert.ok(html.includes('No source document'));
  assert.ok(!html.includes('View statement'));
  assert.ok(!html.includes('undefined'));
});
test('Ask and export retain D response metadata and report missing files', async () => {
  assert.equal((await api.ask('Why did margin change?')).period, '2026-Q3');
  const { buildExport } = await import('./export');
  const docs = await api.documents();
  const result = await buildExport([{ ...docs[0], viewUrl: '' }], [], financialsFixture, '2026-Q3');
  assert.equal(result.summary.documents, 0);
  assert.equal(result.summary.ledgerLines, 0);
  assert.deepEqual(result.summary.missing, [docs[0].filename]);
});
test('low confidence upload routes to review; invalid file is rejected', async () => {
  const doc = await api.upload(new File(['sample'], 'receipt.pdf', { type: 'application/pdf' }), () => {});
  assert.equal(doc.type, 'receipt');
  assert.equal((await api.bills()).find(b => b.docId === doc.id)?.status, 'pending_review');
  await assert.rejects(api.upload(new File(['invalid'], 'file.exe', { type: 'application/octet-stream' }), () => {}), /PDF/);
});
test('ZIP emits local records and a valid end-of-directory count', async () => {
  const result = new DataView(await zip([{ name: 'ledger.csv', data: new TextEncoder().encode('debit,credit\n10,10') }]).arrayBuffer());
  assert.equal(result.getUint32(0, true), 0x04034b50);
  assert.equal(result.getUint32(result.byteLength - 22, true), 0x06054b50);
  assert.equal(result.getUint16(result.byteLength - 14, true), 1);
});
