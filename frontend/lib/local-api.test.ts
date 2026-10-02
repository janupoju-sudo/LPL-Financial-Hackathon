import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeFinancials } from './contracts';

process.env.NEXT_PUBLIC_USE_MOCKS = 'false';
process.env.NEXT_PUBLIC_LOCAL_API = 'true';
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8787';

test('D local endpoints work with real sample data and no Cognito token', async () => {
  const { api } = await import('./api');
  const nativeFetch = globalThis.fetch;
  const paths: string[] = [];
  globalThis.fetch = (input, init) => {
    paths.push(String(input));
    assert.equal(new Headers(init?.headers).get('Authorization'), null);
    return nativeFetch(input, init);
  };
  try {
    const financials = await api.financials('2026-Q3');
    const raw = await nativeFetch('http://localhost:8787/financials?period=2026-Q3').then(r => r.json());
    assert.deepEqual(financials, normalizeFinancials(raw));
    assert.equal(financials.period, '2026-Q3');
    assert.ok(financials.pnl.totalRevenue > 0);
    assert.ok(financials.kpis.margin !== null && financials.kpis.margin < 1);
    const revenue = await api.reconciliation('2026-09');
    assert.equal(revenue.variance, -412);
    assert.ok(revenue.flags[0].message.includes('412'));
    const answer = await api.ask('Why did my margin drop in Q3?');
    assert.ok(answer.answer.includes('Sample answer'));
    assert.ok(answer.citations.length > 0);
    assert.ok(answer.period);
    const source = await api.document('d1');
    assert.equal(source.vendorName, 'Orion Software LLC');
    assert.equal(source.viewUrl, '');
    await assert.rejects(api.document('d3'), /not available/);
    assert.deepEqual(await api.bills(), []);
    assert.deepEqual(await api.rules(), []);
    assert.deepEqual(await api.vendors(), []);
    assert.equal(paths.length, 3);
    await assert.rejects(api.upload(new File(['test'], 'test.pdf', { type: 'application/pdf' }), () => {}), /does not support uploads/);
    const result = await api.export('2026-Q3');
    assert.ok(result.documents > 0);
    assert.ok(result.ledgerLines > 0);
    assert.deepEqual(result.missing, []);
    const download = await nativeFetch(result.downloadUrl);
    assert.equal(download.headers.get('Content-Type'), 'application/zip');
    const zip = new DataView(await download.arrayBuffer());
    assert.equal(zip.getUint32(0, true), 0x04034b50);
    assert.equal(paths.length, 4);
  } finally { globalThis.fetch = nativeFetch; }
});
