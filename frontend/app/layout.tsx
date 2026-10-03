import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Ledgerline | Your practice, in perspective', description: 'The AI back office for independent advisor practices.' };
const themeScript = "try{document.documentElement.dataset.theme=localStorage.getItem('ledgerline-theme')==='dark'?'dark':'light'}catch{document.documentElement.dataset.theme='light'}";
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeScript }} /><link rel="preconnect" href="https://fonts.googleapis.com" /><link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" /><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@500&display=swap" /></head><body>{children}</body></html>; }
