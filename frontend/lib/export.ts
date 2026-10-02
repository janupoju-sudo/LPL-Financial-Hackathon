import type { Bill, Document, Financials } from './types';

// Small ZIP writer using the standard STORE method, so demo exports need no server.
function crc32(bytes: Uint8Array) { let crc = 0xffffffff; for (const byte of bytes) { crc ^= byte; for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0); } return (crc ^ 0xffffffff) >>> 0; }
export function zip(files: { name: string; data: Uint8Array }[]): Blob {
  const chunks: Uint8Array[] = []; const directory: Uint8Array[] = []; let offset = 0; let directorySize = 0;
  for (const file of files) {
    const name = new TextEncoder().encode(file.name); const crc = crc32(file.data);
    const header = new Uint8Array(30 + name.length); const view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true); view.setUint16(4, 20, true); view.setUint16(6, 0x800, true); view.setUint32(14, crc, true); view.setUint32(18, file.data.length, true); view.setUint32(22, file.data.length, true); view.setUint16(26, name.length, true); header.set(name, 30);
    chunks.push(header, file.data);
    const central = new Uint8Array(46 + name.length); const cv = new DataView(central.buffer);
    cv.setUint32(0, 0x02014b50, true); cv.setUint16(4, 20, true); cv.setUint16(6, 20, true); cv.setUint16(8, 0x800, true); cv.setUint32(16, crc, true); cv.setUint32(20, file.data.length, true); cv.setUint32(24, file.data.length, true); cv.setUint16(28, name.length, true); cv.setUint32(42, offset, true); central.set(name, 46);
    directory.push(central); directorySize += central.length; offset += header.length + file.data.length;
  }
  const end = new Uint8Array(22); const ev = new DataView(end.buffer); ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, files.length, true); ev.setUint16(10, files.length, true); ev.setUint32(12, directorySize, true); ev.setUint32(16, offset, true);
  return new Blob([...chunks, ...directory, end].map(bytes => bytes.slice().buffer as ArrayBuffer), { type: 'application/zip' });
}
export async function buildExport(documents: Document[], bills: Bill[], financials: Financials, period: string): Promise<{ blob: Blob; summary: { documents: number; ledgerLines: number; missing: string[] } }> {
  const encode = (text: string) => new TextEncoder().encode(text);
  const csvCell = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`;
  const ledger: (string | number)[][] = [['date', 'account', 'debit', 'credit', 'sourceDocId', 'memo']];
  for (const bill of bills.filter(b => b.status === 'scheduled')) {
    const base = [bill.dueDate, bill.docId ?? '', `Demo payment: ${bill.vendor}`];
    ledger.push([base[0], bill.glAccount, bill.amount, 0, base[1], base[2]], [base[0], '2000 Accounts payable', 0, bill.amount, base[1], base[2]], [base[0], '2000 Accounts payable', bill.amount, 0, base[1], base[2]], [base[0], '1000 Cash', 0, bill.amount, base[1], base[2]]);
  }
  const files = [{ name: 'ledger.csv', data: encode(ledger.map(row => row.map(csvCell).join(',')).join('\r\n')) }, { name: 'financials.json', data: encode(JSON.stringify(financials, null, 2)) }, { name: 'README.txt', data: encode(`SAMPLE - FICTIONAL DATA\nPeriod: ${period}\nDemo export. Ledger contains scheduled demo bills only; financials include seeded history. Uploaded files have simulated extraction. Documents include the full demo library.`) }];
  let included = 0;
  const missing: string[] = [];
  for (const doc of documents) {
    try {
      if (!doc.viewUrl) throw new Error('Missing document URL');
      const response = await fetch(doc.viewUrl);
      if (!response.ok) throw new Error('Document unavailable');
      files.push({ name: `documents/${doc.id}-${doc.filename.replace(/[^a-zA-Z0-9._-]/g, '_')}`, data: new Uint8Array(await response.arrayBuffer()) });
      included++;
    } catch { missing.push(doc.filename); }
  }
  if (missing.length) files[2].data = encode(new TextDecoder().decode(files[2].data) + `\nCould not include: ${missing.join(', ')}`);
  return { blob: zip(files), summary: { documents: included, ledgerLines: ledger.length - 1, missing } };
}
