'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowLeft, ArrowRight, Check } from 'lucide-react';
import { OtterLogo } from '../brand';
import { OtterPeek } from '../otter-peek';
import { ShaderBg } from '../shader-bg';
import { spring, stepVariants } from '../motion';
import { type Answers, DEFAULT_ANSWERS, STEPS, STORAGE_KEY, stepProblem } from './data';
import { BusinessStep, DocumentsStep, PracticeStep, ReadyScreen, RulesStep, SetupScreen, TeamStep } from './steps';

const COPY = [
  { title: 'Tell us about your practice', sub: 'This sets up your own private set of books.' },
  { title: 'How does the business run?', sub: 'Otter uses this to know what each payout should be.' },
  { title: 'Who works with you?', sub: 'Roles decide who can upload, who can approve, and who reviews.' },
  { title: 'Choose your approval rules', sub: 'Otter applies these to every bill, automatically.' },
  { title: 'Bring in your documents', sub: 'Invoices, receipts, W-9s and payout statements. Otter reads them for you.' },
];

type Phase = 'steps' | 'setup' | 'ready';
type Saved = { step: number; answers: Answers };

function load(): Saved | null {
  try { const raw = sessionStorage.getItem(STORAGE_KEY); return raw ? JSON.parse(raw) as Saved : null; } catch { return null; }
}

export function OnboardingWizard({ live, onFinish, onSignIn, onExit }: { live: boolean; onFinish: (email: string) => void; onSignIn: () => void; onExit: () => void }) {
  const [step, setStep] = useState(0);
  const [dir, setDir] = useState(1);
  const [answers, setAnswers] = useState<Answers>(DEFAULT_ANSWERS);
  const [phase, setPhase] = useState<Phase>('steps');
  const [attempted, setAttempted] = useState(false);

  // Restore after a refresh. Read after mount so the server and first client render match.
  // Saving waits until the restore has happened, so it can't overwrite the saved answers with defaults.
  const [restored, setRestored] = useState(false);
  useEffect(() => { const saved = load(); if (saved) { setAnswers({ ...DEFAULT_ANSWERS, ...saved.answers }); setStep(Math.min(saved.step, STEPS.length - 1)); } setRestored(true); }, []);
  useEffect(() => { if (!restored) return; try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ step, answers })); } catch { /* still works without storage */ } }, [restored, step, answers]);

  const problem = stepProblem(step, answers);
  const update = (patch: Partial<Answers>) => setAnswers(a => ({ ...a, ...patch }));
  const go = (to: number) => { setDir(to > step ? 1 : -1); setAttempted(false); setStep(to); };
  const next = () => {
    if (problem) { setAttempted(true); return; }
    if (step === STEPS.length - 1) setPhase('setup'); else go(step + 1);
  };
  const finish = () => { try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ } onFinish(answers.email.trim()); };

  const progress = phase === 'steps' ? (step + (problem ? 0.35 : 0.7)) / STEPS.length : 1;
  const Step = [PracticeStep, BusinessStep, TeamStep, RulesStep, DocumentsStep][step];

  return (
    <div className="ob-shell">
      <ShaderBg animated />
      <header className="ob-top">
        <button type="button" className="ob-logo-btn" onClick={onExit} aria-label="Back to the Otter home page"><OtterLogo height={26} /></button>
        <div className="ob-top-links">
          {phase === 'steps' && <button type="button" className="ob-link" onClick={() => setPhase('setup')}>Skip setup</button>}
          <button type="button" className="ob-link strong" onClick={onSignIn}>Sign in</button>
        </div>
      </header>

      <main className="ob-main">
        <div className="ob-card-wrap">
        {phase === 'ready' && <OtterPeek size={80} right={48} delay={0.9} />}
        <motion.div className="ob-card" layout transition={spring}>
          <div className="ob-progress" aria-hidden><motion.span animate={{ width: `${progress * 100}%` }} transition={spring} /></div>

          {phase === 'steps' && (
            <ol className="ob-steps" aria-label="Setup steps">
              {STEPS.map((s, i) => (
                <li key={s.key} className={i === step ? 'current' : i < step ? 'done' : ''} aria-current={i === step ? 'step' : undefined}>
                  <button type="button" disabled={i > step} onClick={() => i < step && go(i)}>
                    <span className="ob-dot">{i < step ? <Check size={11} /> : i + 1}</span><span className="ob-step-name">{s.name}</span>
                  </button>
                </li>
              ))}
            </ol>
          )}

          <AnimatePresence mode="wait" custom={dir} initial={false}>
            {phase === 'steps' && (
              <motion.form key={step} custom={dir} variants={stepVariants} initial="enter" animate="center" exit="exit"
                className="ob-body" onSubmit={e => { e.preventDefault(); next(); }} noValidate>
                <div className="ob-eyebrow">Step {step + 1} of {STEPS.length}</div>
                <h1>{COPY[step].title}</h1>
                <p className="ob-sub">{COPY[step].sub}</p>
                <Step answers={answers} update={update} />
                <AnimatePresence>{attempted && problem && <motion.p className="ob-error" role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>{problem}</motion.p>}</AnimatePresence>
                <div className="ob-actions">
                  {step > 0 ? <button type="button" className="button ghost" onClick={() => go(step - 1)}><ArrowLeft size={16} />Back</button> : <span />}
                  <motion.button type="submit" className="button primary ob-cta" aria-disabled={Boolean(problem)} whileHover={problem ? undefined : { x: 2 }} whileTap={{ scale: 0.97 }}>
                    {step === STEPS.length - 1 ? 'Finish setup' : 'Continue'}<ArrowRight size={16} />
                  </motion.button>
                </div>
              </motion.form>
            )}
            {phase === 'setup' && <motion.div key="setup" className="ob-body" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.98 }} transition={spring}><SetupScreen onDone={() => setPhase('ready')} /></motion.div>}
            {phase === 'ready' && <motion.div key="ready" className="ob-body" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}><ReadyScreen answers={answers} onOpen={finish} live={live} /></motion.div>}
          </AnimatePresence>
        </motion.div>
        </div>
        <p className="ob-foot">Demo onboarding · SAMPLE — FICTIONAL DATA · Already have an account? <button type="button" className="ob-link strong" onClick={onSignIn}>Sign in</button></p>
      </main>
    </div>
  );
}
