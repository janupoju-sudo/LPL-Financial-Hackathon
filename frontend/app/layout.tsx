import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Ledgerline | Your practice, in perspective', description: 'The AI back office for independent advisor practices.' };
const themeScript = "try{document.documentElement.dataset.theme=localStorage.getItem('ledgerline-theme')==='dark'?'dark':'light'}catch{document.documentElement.dataset.theme='light'}";
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head><body>{children}</body></html>; }
