'use client';

import { motion, useReducedMotion } from 'motion/react';

// One loop: wait, pop up, bob, look left and right, duck back down. Times are fractions of LOOP seconds.
const LOOP = 10;
const times = [0, 0.08, 0.16, 0.21, 0.26, 0.34, 0.44, 0.52, 0.62, 0.7, 1];
const y = ['110%', '110%', '0%', '-4%', '0%', '0%', '-2%', '0%', '0%', '110%', '110%'];
const rotate = [0, 0, 0, 0, 0, -8, 7, 0, 0, 0, 0];
const blink = { scaleY: [1, 1, 0.1, 1, 1, 0.1, 1, 1], times: [0, 0.38, 0.395, 0.41, 0.56, 0.575, 0.59, 1] };

/**
 * An otter head (drawn like the logo) that peeks over the top edge of whatever it sits on.
 * Place it inside a `position: relative` card; it sits just above the card's top edge, behind the card.
 */
export function OtterPeek({ size = 88, right = 40, delay = 1.2 }: { size?: number; right?: number; delay?: number }) {
  const reduce = useReducedMotion();
  const loop = { duration: LOOP, times, repeat: Infinity, ease: 'easeInOut' as const, delay };
  return (
    <div className="otter-peek" style={{ right, width: size * 1.27, height: size }} aria-hidden="true">
      <motion.svg viewBox="0 0 160 150" width={size} style={{ left: size * 0.135 }}
        initial={{ y: reduce ? '12%' : '110%' }}
        animate={reduce ? { y: '12%' } : { y, rotate }}
        transition={reduce ? { duration: 0 } : loop}>
        <path d="M22 150 C16 104 26 52 80 44 C134 52 144 104 138 150 Z" className="otter-fur" />
        <circle cx="38" cy="58" r="12" className="otter-fur" /><circle cx="38" cy="58" r="5.5" className="otter-fur-dark" />
        <circle cx="122" cy="58" r="12" className="otter-fur" /><circle cx="122" cy="58" r="5.5" className="otter-fur-dark" />
        <path d="M44 120 C42 96 58 84 80 84 C102 84 118 96 116 120 C114 140 100 150 80 150 C60 150 46 140 44 120 Z" className="otter-belly" />
        {[60, 100].map(cx => (
          <motion.g key={cx} style={{ transformBox: 'fill-box', transformOrigin: 'center' }} animate={reduce ? undefined : { scaleY: blink.scaleY }} transition={reduce ? undefined : { duration: LOOP, times: blink.times, repeat: Infinity, delay }}>
            <circle cx={cx} cy="80" r="6.5" className="otter-eye" /><circle cx={cx + 2.2} cy="77.8" r="2" fill="#fff" />
          </motion.g>
        ))}
        <path d="M70 97 Q80 91 90 97 Q88 106 80 107 Q72 106 70 97 Z" className="otter-eye" />
        <path d="M80 107 V112 M71 114 Q76 118 80 112 Q84 118 89 114" fill="none" className="otter-line" strokeWidth="2.2" strokeLinecap="round" />
        <g className="otter-line" strokeWidth="1.2" strokeLinecap="round" opacity=".7">
          <path d="M64 108 L26 100" /><path d="M64 112 L24 114" /><path d="M65 116 L30 126" />
          <path d="M96 108 L134 100" /><path d="M96 112 L136 114" /><path d="M95 116 L130 126" />
        </g>
      </motion.svg>
    </div>
  );
}
