'use client';

import { useEffect } from 'react';
import { animate, inView } from 'motion';

// Everything that looks like a button gets the same springy press, without wrapping each one in motion.button.
const PRESSABLE = [
  '.button', '.lp-pill', '.icon-button', '.nav-item', '.side-link', '.subnav a', '.ask-fab', '.topbar-search',
  '.suggestions button', '.chat-suggestions button', '.document-link', '.ob-chip', '.ob-add', '.ob-rule', '.ob-roles button',
  '.settings-signout', '.theme-switch', '.profile-trigger', '.segmented button', '.tabs button', '.documents-summary button',
].join(', ');

// App cards that fade up as they scroll into view.
const REVEAL = '.content .panel, .content .kpi, .content .insight-card, .content .rule-card, .content .stat-card';

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const pressIn = { type: 'spring', stiffness: 700, damping: 32 } as const;
const pressOut = { type: 'spring', stiffness: 420, damping: 14 } as const;

/** Mount once near the root: every button-like element shrinks a little on press and springs back. */
export function PressFeedback() {
  useEffect(() => {
    const onDown = (event: PointerEvent) => {
      if (event.button !== 0 || reduced()) return;
      const el = (event.target as Element | null)?.closest<HTMLElement>(PRESSABLE);
      if (!el || el.matches(':disabled, [aria-disabled="true"]')) return;
      animate(el, { scale: 0.96 }, pressIn);
      const release = () => {
        animate(el, { scale: 1 }, pressOut);
        window.removeEventListener('pointerup', release);
        window.removeEventListener('pointercancel', release);
      };
      window.addEventListener('pointerup', release);
      window.addEventListener('pointercancel', release);
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, []);
  return null;
}

/** Inside the app: cards fade up as they enter the screen, and each page change fades the content in. */
export function RevealOnScroll({ path }: { path: string }) {
  useEffect(() => {
    if (reduced()) return;
    const content = document.querySelector<HTMLElement>('.content');
    if (content) animate(content, { opacity: [0, 1], y: [8, 0] }, { duration: 0.35, ease: [0.22, 1, 0.36, 1] });
  }, [path]);

  useEffect(() => {
    if (reduced()) return;
    const seen = new WeakSet<Element>();
    const stops: (() => void)[] = [];
    let batch = 0; let frame = 0;
    const register = () => {
      document.querySelectorAll<HTMLElement>(REVEAL).forEach(el => {
        if (seen.has(el)) return;
        seen.add(el);
        el.style.opacity = '0';
        stops.push(inView(el, () => {
          // Cards that appear together are staggered slightly, top to bottom.
          const delay = Math.min(batch++, 6) * 0.05;
          cancelAnimationFrame(frame); frame = requestAnimationFrame(() => { batch = 0; });
          animate(el, { opacity: [0, 1], y: [18, 0] }, { duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] });
        }, { margin: '0px 0px -40px 0px' }));
      });
    };
    register();
    const observer = new MutationObserver(register);
    const root = document.querySelector('.main-area');
    if (root) observer.observe(root, { childList: true, subtree: true });
    return () => { observer.disconnect(); stops.forEach(stop => stop()); cancelAnimationFrame(frame); };
  }, []);
  return null;
}
