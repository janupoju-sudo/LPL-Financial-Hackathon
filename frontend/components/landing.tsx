'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, FileText, Lock, MessageSquareText, Scale, ShieldCheck, SlidersHorizontal, UsersRound } from 'lucide-react';
import { OtterLogo } from './brand';
import { ease, fadeUp, spring, stagger } from './motion';
import { OtterPeek } from './otter-peek';
import { ShaderBg } from './shader-bg';

const FEATURES = [
  { icon: FileText, title: 'Documents in, books done', body: 'Drop an invoice, receipt or W-9. Otter reads it, matches the vendor and drafts the bill.' },
  { icon: SlidersHorizontal, title: 'Rules that approve for you', body: 'Small bills from known vendors go straight through. Big ones wait for a partner.' },
  { icon: Scale, title: 'Every payout, checked', body: 'Each payout statement is matched to your fee schedule, so a short trail never slips by.' },
  { icon: MessageSquareText, title: 'Ask Otter', body: '"Why did my margin drop?" Get the answer with links to the documents behind it.' },
];

const TRUST = [
  { icon: Lock, label: 'Documents locked on upload' },
  { icon: UsersRound, label: 'Role-based approvals' },
  { icon: ShieldCheck, label: 'Full audit trail' },
];

// The hero card loops through one bill's life: invoice read → bill drafted → approved.
const STAGES = ['Reading invoice', 'Bill drafted', 'Approved automatically'] as const;

function BillCard() {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState(2);
  useEffect(() => {
    if (reduce) return;
    const t = setTimeout(() => setStage(s => (s + 1) % STAGES.length), stage === 2 ? 3200 : 1600);
    return () => clearTimeout(t);
  }, [stage, reduce]);
  return (
    <motion.div className="lp-bill-wrap" initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, delay: 0.3, ease }}>
      <OtterPeek />
      <div className="lp-bill">
        <div className="lp-bill-head"><span>orion_invoice_0918.pdf</span><span>Just now</span></div>
        {[['Vendor', 'Orion Software LLC'], ['Category', '6310 · Software'], ['Amount', '$450.00']].map(([k, v], i) => (
          <div key={k} className="lp-row"><span>{k}</span><strong>{stage === 0 && i > 0 ? <span className="lp-shimmer" /> : v}</strong></div>
        ))}
        <AnimatePresence mode="wait">
          <motion.span key={stage} className={`lp-status s${stage}`} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2 }}>
            {stage === 2 ? <Check size={13} /> : <span className="lp-pulse" />}{STAGES[stage]}
          </motion.span>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

export function Landing({ onStart, onSignIn }: { onStart: () => void; onSignIn: () => void }) {
  return (
    <div className="lp">
      <ShaderBg animated />
      <motion.header className="lp-nav" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}>
        <OtterLogo height={26} />
        <nav className="lp-links" aria-label="Sections"><a href="#how">How it works</a><a href="#security">Security</a></nav>
        <div className="lp-nav-actions">
          <button type="button" className="lp-pill" onClick={onSignIn}>Sign in</button>
          <motion.button type="button" className="lp-pill dark" onClick={onStart} whileTap={{ scale: 0.97 }}>Get started</motion.button>
        </div>
      </motion.header>

      <main>
        <section className="lp-hero">
          <motion.div variants={stagger(0.1, 0.1)} initial="hidden" animate="show">
            <motion.h1 variants={fadeUp}>Your practice&apos;s books, done for you</motion.h1>
            <motion.p variants={fadeUp}>Otter reads every invoice, routes it for approval and checks every payout, so you can spend the day with clients.</motion.p>
            <motion.div variants={fadeUp} className="lp-ctas">
              <motion.button type="button" className="lp-pill dark lg" onClick={onStart} whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>Set up your practice</motion.button>
              <a className="lp-pill light lg" href="#how">See how it works</a>
            </motion.div>
          </motion.div>
          <BillCard />
        </section>

        <motion.div id="security" className="lp-trust" variants={stagger(0.08, 0.6)} initial="hidden" animate="show">
          {TRUST.map(({ icon: Icon, label }) => <motion.span key={label} variants={fadeUp}><Icon size={16} />{label}</motion.span>)}
        </motion.div>

        <section id="how" className="lp-section">
          <motion.h2 variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.6 }}>One quiet back office for the whole practice</motion.h2>
          <motion.div className="lp-features" variants={stagger(0.09)} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }}>
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <motion.article key={title} variants={fadeUp} className="lp-feature" whileHover={{ y: -4 }} transition={spring}>
                <span className="lp-feature-icon"><Icon size={19} /></span>
                <h3>{title}</h3>
                <p>{body}</p>
              </motion.article>
            ))}
          </motion.div>
        </section>

        <motion.section className="lp-closing" variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.5 }}>
          <h2>Ready when you are</h2>
          <motion.button type="button" className="lp-pill dark lg" onClick={onStart} whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>Get started<ArrowRight size={17} /></motion.button>
        </motion.section>
      </main>

      <footer className="lp-footer"><span>© 2026 Otter · Built for the LPL Financial Hackathon · Sample, fictional data</span><button type="button" className="ob-link strong" onClick={onSignIn}>Sign in</button></footer>
    </div>
  );
}
