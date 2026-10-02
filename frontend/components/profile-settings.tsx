'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { Moon, Settings, Sun, X } from 'lucide-react';

const THEME_KEY = 'ledgerline-theme';

export function ProfileSettings({ role, compact = false }: { role: string; compact?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [dark, setDark] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const sync = () => setDark(document.documentElement.dataset.theme === 'dark');
    const onStorage = (event: StorageEvent) => {
      if (event.key !== THEME_KEY) return;
      document.documentElement.dataset.theme = event.newValue === 'dark' ? 'dark' : 'light';
      sync();
    };
    sync();
    window.addEventListener('ledgerline-theme-change', sync);
    window.addEventListener('storage', onStorage);
    return () => { window.removeEventListener('ledgerline-theme-change', sync); window.removeEventListener('storage', onStorage); };
  }, []);

  const toggleTheme = () => {
    const theme = dark ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem(THEME_KEY, theme); } catch { /* The toggle still works if browser storage is disabled. */ }
    window.dispatchEvent(new Event('ledgerline-theme-change'));
  };

  return <>
    <button type="button" className={`profile-trigger ${compact ? 'compact' : ''}`} aria-label="Open profile settings" aria-haspopup="dialog" aria-expanded={open} onClick={() => { dialog.current?.showModal(); setOpen(true); }}>
      <span className={`user-avatar ${compact ? 'small' : ''}`}>MC</span>
      {!compact && <><span className="profile-name"><strong>Maya Chen</strong><small>{role}</small></span><Settings size={16} /></>}
    </button>
    <dialog ref={dialog} className="settings-dialog" aria-labelledby={titleId} onClose={() => setOpen(false)} onClick={event => {
      if (event.target !== event.currentTarget) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.current?.close();
    }}>
      <div className="settings-heading"><div><div className="eyebrow">MAKE YOURSELF AT HOME</div><h2 id={titleId}>Your settings</h2></div><button type="button" autoFocus className="settings-close" aria-label="Close settings" onClick={() => dialog.current?.close()}><X size={20} /></button></div>
      <div className="settings-account"><span className="user-avatar">MC</span><div><strong>Maya Chen</strong><small>{role}</small></div></div>
      <h3 className="settings-section-title">Appearance</h3>
      <div className="theme-setting"><span className="theme-setting-icon">{dark ? <Moon size={20} /> : <Sun size={20} />}</span><div><strong>Dark mode</strong><p>A softer view for after hours.</p></div><button type="button" role="switch" aria-label="Dark mode" aria-checked={dark} className={`theme-switch ${dark ? 'enabled' : ''}`} onClick={toggleTheme}><span /></button></div>
      <p className="settings-note">Your appearance preference is saved in this browser.</p>
    </dialog>
  </>;
}
