import type { Transition, Variants } from 'motion/react';

// One spring and one set of variants, so the landing page and the wizard move the same way.
export const spring: Transition = { type: 'spring', stiffness: 260, damping: 30, mass: 0.9 };
export const softSpring: Transition = { type: 'spring', stiffness: 140, damping: 22 };
export const ease = [0.22, 1, 0.36, 1] as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18, filter: 'blur(6px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.6, ease } },
};

export const stagger = (gap = 0.08, delay = 0): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: gap, delayChildren: delay } },
});

// Steps slide in the direction you're going: forward from the right, back from the left.
export const stepVariants: Variants = {
  enter: (dir: number) => ({ opacity: 0, x: dir * 48, filter: 'blur(4px)' }),
  center: { opacity: 1, x: 0, filter: 'blur(0px)', transition: { ...spring, opacity: { duration: 0.25 } } },
  exit: (dir: number) => ({ opacity: 0, x: dir * -48, filter: 'blur(4px)', transition: { duration: 0.2, ease } }),
};
