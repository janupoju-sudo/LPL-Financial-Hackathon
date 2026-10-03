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
import type { Financials, Reconciliation, Role } from './types';
import { normalizeBillDetail, normalizeFinancials, normalizeReconciliation, type LegacyFinancials } from './contracts';
import { validateLocalApi } from './local-mode';
import { canApproveBill, canImportTransactions, canManageRules, canReviewDocuments, canUploadDocuments } from './permissions';

test('role capabilities match the practice permission policy', () => {
  const ownerAndOps: Role[] = ['owner', 'ops'];
  assert.deepEqual(ownerAndOps.filter(canUploadDocuments), ownerAndOps);
  assert.deepEqual(ownerAndOps.filter(canReviewDocuments), ownerAndOps);
  assert.deepEqual(ownerAndOps.filter(canImportTransactions), ownerAndOps);
  assert.equal(canManageRules('owner'), true);
  for (const role of ['partner', 'lpl_bookkeeper'] as const) {
    assert.equal(canUploadDocuments(role), false);
    assert.equal(canReviewDocuments(role), false);
    assert.equal(canImportTransactions(role), false);
    assert.equal(canManageRules(role), false);
  }
  assert.equal(canManageRules('ops'), false);
  assert.equal(canUploadDocuments('ops'), true);
  assert.equal(canReviewDocuments('ops'), true);
  assert.equal(canImportTransactions('ops'), true);
  assert.equal(canApproveBill('owner', ['partner'], 'uploader', 'owner-user'), true);
  assert.equal(canApproveBill('owner', ['partner'], 'owner-user', 'owner-user'), false);
  assert.equal(canApproveBill('partner', ['partner'], 'uploader', 'partner-user'), true);
  assert.equal(canApproveBill('partner', ['owner'], 'uploader', 'partner-user'), false);
  assert.equal(canApproveBill('ops', ['ops'], 'uploader', 'ops-user'), false);
  assert.equal(canApproveBill('lpl_bookkeeper', ['lpl_bookkeeper'], 'uploader', 'bookkeeper'), false);
});

test('approval enforces role, unblocks on vendor documents, and updates balanced financials', async () => {
  const before = await api.financials('2026-Q3');
  await assert.rejects(api.decision('b1', 'approve', '', 'ops'), /Switch/);
  await assert.rejects(api.decision('b2', 'approve', '', 'partner'), /W-9/);
  await api.upload(new File(['sample'], 'brightline-w9.pdf', { type: 'application/pdf' }), () => {});
  await assert.rejects(api.decision('b2', 'approve', '', 'partner'), /W-9/);
  await api.upload(new File(['sample'], 'brightline-void-check.pdf', { type: 'application/pdf' }), () => {});
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
test('authentication bypass is limited to explicit loopback APIs', () => {
  assert.equal(validateLocalApi('http://localhost:8787/'), 'http://localhost:8787');
  assert.equal(validateLocalApi('http://127.0.0.1:8787'), 'http://127.0.0.1:8787');
  assert.throws(() => validateLocalApi('https://api.example.com'), /loopback/);
  assert.throws(() => validateLocalApi('http://localhost.evil.example'), /loopback/);
  assert.throws(() => validateLocalApi(undefined), /Set NEXT_PUBLIC_API_URL/);
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

test('live API payloads (C backend shape) normalize to frontend types', async () => {
  const { normalizeBill, normalizeDocument, normalizeRule, normalizeVendor, toApiRule } = await import('./contracts');
  const doc = normalizeDocument({ documentId: 'doc-1', type: 'invoice', filename: 'orion.pdf', status: 'processed', vendorName: 'Orion Software', amount: 1850, createdAt: '2026-09-12T10:00:00Z', confidence: 0.94, extracted: {}, viewUrl: '' });
  assert.equal(doc.id, 'doc-1');
  assert.equal('documentId' in doc, false);
  const bill = normalizeBill({
    billId: 'bill-1', documentId: 'doc-1', vendorId: 'ven-1', vendorName: 'Brightline Marketing', amount: 650, dueDate: '2026-10-18',
    glAccount: '6500', glAccountName: 'Marketing', glAccountReason: "Matched vendor memory: Brightline Marketing uses expense account 6500.", status: 'pending_approval',
    ruleHits: [{ ruleId: 'r-docs', name: 'Vendor docs', action: 'hold', reason: 'Vendor is missing a W-9 or void check' }, 'Legacy text hit'],
  });
  assert.deepEqual(bill, {
    id: 'bill-1', docId: 'doc-1', vendor: 'Brightline Marketing', vendorId: 'ven-1', amount: 650, dueDate: '2026-10-18',
    glAccount: '6500 · Marketing', glAccountReason: "Matched vendor memory: Brightline Marketing uses expense account 6500.", status: 'pending_approval', ruleHits: ['Vendor is missing a W-9 or void check', 'Legacy text hit'],
  });
  assert.ok(bill.ruleHits.some(hit => hit.includes('missing')));   // the approve-button guard still works
  assert.equal(normalizeVendor({ vendorId: 'ven-1', name: 'Orion', defaultGlAccount: '6300', hasW9: true, hasVoidCheck: true, billCount: 2 }).id, 'ven-1');
  const rule = normalizeRule({ ruleId: 'r-docs', name: 'Vendor docs', condition: { field: 'vendor.hasW9', op: 'eq', value: false }, action: 'hold', approverRole: 'owner' });
  assert.equal(rule.id, 'r-docs');
  assert.equal(rule.action, 'require_docs');
  assert.equal(toApiRule({ ...rule, action: 'require_docs' }).action, 'hold');
});

test('bill detail keeps the audit trail and payment from the live API', () => {
  const detail = normalizeBillDetail({ billId: 'bill_1', vendorName: 'Orion Software LLC', amount: 1850, status: 'scheduled', glAccount: '6300', glAccountName: 'Technology', requiredApprovers: ['partner'], audit: [{ at: '2026-07-16T10:12:00+00:00', actor: 'raj@harborpoint.example', action: 'approved', detail: 'Approved' }], payment: { method: 'ACH (mock)', scheduledFor: '2026-07-25', confirmation: 'MOCK-1' } });
  assert.equal(detail.id, 'bill_1');
  assert.equal(detail.glAccount, '6300 · Technology');
  assert.deepEqual(detail.requiredApprovers, ['partner']);
  assert.equal(detail.audit[0].actor, 'raj@harborpoint.example');
  assert.equal(detail.payment?.scheduledFor, '2026-07-25');
});

test('deleting a rule removes it from the list (mock mode)', async () => {
  const before = await api.rules();
  await api.deleteRule(before[0].id);
  const after = await api.rules();
  assert.equal(after.length, before.length - 1);
  assert.ok(!after.some(r => r.id === before[0].id));
});
