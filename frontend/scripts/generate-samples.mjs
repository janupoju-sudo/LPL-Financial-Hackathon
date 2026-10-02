import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const docs = JSON.parse(fs.readFileSync(path.join(root, 'mocks/documents.json'), 'utf8'));
function pdf(lines) {
  const escape = text => String(text).replace(/[^\x20-\x7e]/g, '-').replace(/[\\()]/g, '\\$&');
  const content = `BT /F1 12 Tf 55 760 Td 22 TL ${lines.map((line, i) => `${i ? 'T* ' : ''}(${escape(line)}) Tj`).join('\n')} ET`;
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>', '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}\nendstream`];
  let output = '%PDF-1.4\n'; const offsets = [0];
  objects.forEach((object, i) => { offsets.push(Buffer.byteLength(output)); output += `${i + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(output);
  output += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(n => `${String(n).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return output;
}
for (const doc of docs) {
  doc.viewUrl = `/sample-${doc.id}.pdf`;
  const lines = ['SAMPLE - FICTIONAL DATA', '', 'HARBOR POINT WEALTH', doc.filename, '', ...Object.entries(doc.extracted).map(([key, value]) => `${key}: ${value}`), '', 'Generated solely for the Ledgerline hackathon demo.'];
  fs.writeFileSync(path.join(root, 'public', doc.viewUrl), pdf(lines));
}
fs.writeFileSync(path.join(root, 'mocks/documents.json'), JSON.stringify(docs, null, 2) + '\n');
