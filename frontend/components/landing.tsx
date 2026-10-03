'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, FileText, Lock, MessageSquareText, Scale, ShieldCheck, SlidersHorizontal, Sparkles, UsersRound } from 'lucide-react';
import { OtterLogo } from './brand';
import { ease, fadeUp, spring, stagger } from './motion';

const FEATURES = [
  { icon: FileText, title: 'Documents in, books done', body: 'Drop an invoice, receipt or W-9. Otter reads it, matches the vendor and drafts the bill.' },
  { icon: SlidersHorizontal, title: 'Rules that approve for you', body: 'Small bills from known vendors go straight through. Big ones wait for a partner.' },
  { icon: Scale, title: 'Every payout, checked', body: 'Each LPL payout is matched to your fee schedule, so a short trail never slips by.' },
  { icon: MessageSquareText, title: 'Ask your books', body: '"Why did my margin drop?" Get the answer with links to the documents behind it.' },
];

const TRUST = [
  { icon: Lock, label: 'Documents locked on upload (S3 Object Lock)' },
  { icon: UsersRound, label: 'Role-based approvals, no self-approval' },
  { icon: ShieldCheck, label: 'Full audit trail on every bill' },
];

// The hero card loops through one bill's life: invoice read → bill drafted → approved.
const STAGES = ['Reading invoice', 'Bill drafted', 'Approved'] as const;

function PreviewCard() {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (reduce) { setStage(2); return; }
    const t = setTimeout(() => setStage(s => (s + 1) % STAGES.length), stage === 2 ? 2600 : 1700);
    return () => clearTimeout(t);
  }, [stage, reduce]);
  return (
    <motion.div className="lp-preview" initial={{ opacity: 0, y: 30, rotate: -1.5 }} animate={{ opacity: 1, y: 0, rotate: 0 }} transition={{ duration: 0.9, delay: 0.35, ease }}>
      <div className="lp-preview-head">
        <span className="lp-file"><FileText size={15} />orion_invoice_0918.pdf</span>
        <AnimatePresence mode="wait">
          <motion.span key={stage} className={`lp-status s${stage}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
            {stage === 2 ? <Check size={13} /> : <span className="lp-pulse" />}{STAGES[stage]}
          </motion.span>
        </AnimatePresence>
      </div>
      <div className="lp-rows">
        {[['Vendor', 'Orion Software LLC'], ['Invoice', 'INV-20931'], ['Category', '6310 · Software'], ['Amount', '$450.00']].map(([k, v], i) => (
          <div key={k} className="lp-row">
            <span>{k}</span>
            <motion.strong animate={{ opacity: stage >= 1 || i < 2 ? 1 : 0.25 }} transition={{ duration: 0.3, delay: i * 0.06 }}>{stage === 0 && i >= 2 ? <span className="lp-shimmer" /> : v}</motion.strong>
          </div>
        ))}
      </div>
      <div className="lp-preview-foot">
        <span className="lp-chip"><Sparkles size={13} />Recognized vendor · 6 prior bills</span>
        <AnimatePresence>{stage === 2 && <motion.span className="lp-chip ok" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={spring}>Under $1,000 · auto-approved</motion.span>}</AnimatePresence>
      </div>
    </motion.div>
  );
}

export function Landing({ onStart, onSignIn }: { onStart: () => void; onSignIn: () => void }) {
  return (
    <div className="lp">
      <div className="ob-blobs" aria-hidden><span /><span /><span /></div>
      <motion.header className="lp-nav" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}>
        <OtterLogo height={28} />
        <div className="lp-nav-actions">
          <button type="button" className="button ghost" onClick={onSignIn}>Sign in</button>
          <motion.button type="button" className="button primary" onClick={onStart} whileTap={{ scale: 0.97 }}>Get started</motion.button>
        </div>
      </motion.header>

      <main>
        <section className="lp-hero">
          <motion.div className="lp-hero-copy" variants={stagger(0.1, 0.1)} initial="hidden" animate="show">
            <motion.span variants={fadeUp} className="lp-kicker"><span className="lp-dot" />The AI back office for LPL advisors</motion.span>
            <motion.h1 variants={fadeUp}>Your practice&apos;s books, <em>done for you.</em></motion.h1>
            <motion.p variants={fadeUp}>Otter reads every invoice, routes it for approval, checks every LPL payout and keeps your P&amp;L current, so you can spend the day with clients.</motion.p>
            <motion.div variants={fadeUp} className="lp-cta-row">
              <motion.button type="button" className="button primary lp-cta" onClick={onStart} whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>Set up your practice<ArrowRight size={17} /></motion.button>
              <button type="button" className="button outline lp-cta" onClick={onSignIn}>I have an account</button>
            </motion.div>
            <motion.small variants={fadeUp} className="lp-fine">Takes about two minutes · runs on AWS</motion.small>
          </motion.div>
          <PreviewCard />
        </section>

        <motion.section className="lp-features" variants={stagger(0.09)} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.25 }}>
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <motion.article key={title} variants={fadeUp} className="lp-feature" whileHover={{ y: -4 }} transition={spring}>
              <span className="lp-feature-icon"><Icon size={19} /></span>
              <h3>{title}</h3>
              <p>{body}</p>
            </motion.article>
          ))}
        </motion.section>

        <motion.section className="lp-trust" variants={stagger(0.08)} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.4 }}>
          {TRUST.map(({ icon: Icon, label }) => <motion.span key={label} variants={fadeUp}><Icon size={15} />{label}</motion.span>)}
        </motion.section>

        <motion.section className="lp-closing" variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.5 }}>
          <h2>Ready when you are.</h2>
          <motion.button type="button" className="button primary lp-cta" onClick={onStart} whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}>Get started<ArrowRight size={17} /></motion.button>
        </motion.section>
      </main>

      <footer className="lp-footer"><span>© 2026 Otter · Built for the LPL Financial Hackathon · SAMPLE — FICTIONAL DATA</span><button type="button" className="ob-link strong" onClick={onSignIn}>Sign in</button></footer>
    </div>
  );
}
