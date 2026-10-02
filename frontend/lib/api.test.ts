import { test } from 'node:test';
import assert from 'node:assert/strict';
import { api } from './api';
import { zip } from './export';

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
  assert.equal(after.pnl.expenses - before.pnl.expenses, 4300);
  assert.equal(before.pnl.netIncome - after.pnl.netIncome, 4300);
  assert.equal(after.balanceSheet.assets, after.balanceSheet.equity + after.balanceSheet.liabilities);
  assert.equal(before.cashFlow.net - after.cashFlow.net, 4300);
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
