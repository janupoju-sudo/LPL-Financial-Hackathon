import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Ledgerline | Your practice, in perspective', description: 'The AI back office for independent advisor practices.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
