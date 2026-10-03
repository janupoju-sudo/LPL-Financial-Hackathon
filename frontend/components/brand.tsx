export const PRODUCT = 'Otter';

// The logo art is used as a mask, so it takes the brand colour (--accent: fur brown, oat in dark mode).
export function OtterMark({ size = 30, className = '' }: { size?: number; className?: string }) {
  return <span role="img" aria-hidden="true" className={`otter-art otter-mark ${className}`} style={{ width: size, height: size }} />;
}

export function OtterLogo({ height = 30, className = '' }: { height?: number; className?: string }) {
  return <span role="img" aria-label={PRODUCT} className={`otter-art otter-logo ${className}`} style={{ height, width: height * 3.2 }} />;
}
