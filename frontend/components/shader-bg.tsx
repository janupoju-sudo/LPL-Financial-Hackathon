'use client';

import { useEffect, useState } from 'react';
import { MeshGradient } from '@paper-design/shaders-react';

// "Otter in the river": cream paper, oat, soft water green. Dark is the same river at night.
const COLORS = {
  light: ['#f6f1e7', '#e5d6bf', '#dde3d3', '#efe7d9', '#cbd5c4'],
  dark: ['#14110d', '#2a2118', '#1b2620', '#201a13', '#24302a'],
};

function useTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const sync = () => setDark(document.documentElement.dataset.theme === 'dark');
    sync();
    window.addEventListener('ledgerline-theme-change', sync);
    window.addEventListener('storage', sync);
    return () => { window.removeEventListener('ledgerline-theme-change', sync); window.removeEventListener('storage', sync); };
  }, []);
  return dark;
}

// Moving only when asked, the tab is visible and the viewer hasn't asked for reduced motion.
function useMotionAllowed(animated: boolean) {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    if (!animated) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => setAllowed(!media.matches && document.visibilityState === 'visible');
    sync();
    media.addEventListener('change', sync);
    document.addEventListener('visibilitychange', sync);
    return () => { media.removeEventListener('change', sync); document.removeEventListener('visibilitychange', sync); };
  }, [animated]);
  return allowed;
}

function hasWebGL() {
  try { const c = document.createElement('canvas'); return Boolean(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}

/** Full-screen shader background. The CSS gradient underneath shows until WebGL is ready, or for good without it. */
export function ShaderBg({ animated = false }: { animated?: boolean }) {
  const dark = useTheme();
  const moving = useMotionAllowed(animated);
  const [webgl, setWebgl] = useState(false);
  useEffect(() => setWebgl(hasWebGL()), []);
  return (
    <div className="shader-bg" aria-hidden="true">
      {webgl && <MeshGradient className="shader-bg-canvas" colors={dark ? COLORS.dark : COLORS.light} distortion={0.8} swirl={0.25} grainOverlay={dark ? 0.04 : 0.05} speed={moving ? 0.2 : 0} frame={4000} maxPixelCount={1920 * 1080} minPixelRatio={1} />}
    </div>
  );
}
