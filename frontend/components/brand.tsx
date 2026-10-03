/* eslint-disable @next/next/no-img-element */
export const PRODUCT = 'Otter';

// Logo art is dark ink on transparent; .otter-art flips it for dark mode.
export function OtterMark({ size = 30, className = '' }: { size?: number; className?: string }) {
  return <img src="/otter-mark.png" alt="" width={size} height={size} className={`otter-art ${className}`} />;
}

export function OtterLogo({ height = 30, className = '' }: { height?: number; className?: string }) {
  return <img src="/otter-logo.png" alt={PRODUCT} height={height} style={{ height, width: 'auto' }} className={`otter-art ${className}`} />;
}
