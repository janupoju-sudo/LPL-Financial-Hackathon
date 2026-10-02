import type { Document } from './types';

// Metadata from backend/tests/fixtures.py. D's dev server has no document route;
// these sources intentionally have no preview or simulated extraction fields.
export const localDocuments: Document[] = [
  { id: 'd1', type: 'invoice', filename: 'Orion_INV-2291.pdf', vendorName: 'Orion Software LLC', amount: 1240, createdAt: '2026-09-29' },
  { id: 'rent-2026-07', type: 'invoice', filename: 'Seaport_Lease_Amendment_Q3.pdf', vendorName: 'Seaport Office Partners', amount: 9800, createdAt: '2026-07-01' },
  { id: 'clearpath-2026-09', type: 'invoice', filename: 'Clearpath_Compliance_0917.pdf', vendorName: 'Clearpath Compliance', amount: 850, createdAt: '2026-09-17' },
  { id: 'payout-2026-09', type: 'payout_statement', filename: 'LPL_Payout_Sep2026.pdf', vendorName: 'LPL Financial', amount: 218000, createdAt: '2026-09-30' },
  { id: 'w9-orion', type: 'w9', filename: 'Orion_W9.pdf', vendorName: 'Orion Software LLC', amount: 0, createdAt: '2026-06-12' }
].map(doc => ({ ...doc, type: doc.type as Document['type'], status: 'sample', confidence: 0, extracted: { vendor: doc.vendorName, filename: doc.filename, createdAt: doc.createdAt, amount: doc.amount }, viewUrl: '' }));
