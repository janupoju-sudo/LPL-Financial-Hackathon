'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Building2, Check, FileText, Link2, Plus, ShieldCheck, Trash2, UploadCloud, UserRound } from 'lucide-react';
import { fadeUp, spring, stagger } from '../motion';
import { type Answers, type Member, type TeamRole, REVENUE_TYPES, ROLE_INFO, SETUP_TASKS, STARTER_RULES } from './data';

type StepProps = { answers: Answers; update: (patch: Partial<Answers>) => void };

const Item = motion.div;

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <Item variants={fadeUp} className="ob-field"><label><span>{label}</span>{children}</label>{hint && <small>{hint}</small>}</Item>;
}

export function PracticeStep({ answers, update }: StepProps) {
  return (
    <motion.div className="ob-fields" variants={stagger(0.06)} initial="hidden" animate="show">
      <Field label="Practice name"><input autoFocus value={answers.practiceName} onChange={e => update({ practiceName: e.target.value })} placeholder="e.g. Harbor Point Wealth" /></Field>
      <div className="ob-row">
        <Field label="Your name"><input value={answers.yourName} onChange={e => update({ yourName: e.target.value })} placeholder="First and last name" /></Field>
        <Field label="Work email" hint="You'll sign in with this."><input type="email" value={answers.email} onChange={e => update({ email: e.target.value })} placeholder="you@practice.com" /></Field>
      </div>
      <Item variants={fadeUp} className="ob-note"><Building2 size={16} />Affiliated with LPL Financial. Your books stay separate from every other practice.</Item>
    </motion.div>
  );
}

const fmtAum = (m: number) => m >= 1000 ? `$${+(m / 1000).toFixed(2)}B` : `$${m}M`;
// AUM runs $1M–$2B, so the slider is logarithmic: each stretch of track covers 10x the one before,
// which keeps small practices as easy to pick as large ones. Values snap to round numbers.
const AUM_MIN = 1, AUM_MAX = 2000, SLIDER_STEPS = 1000;
const aumToPos = (m: number) => Math.round(Math.log(Math.min(Math.max(m, AUM_MIN), AUM_MAX) / AUM_MIN) / Math.log(AUM_MAX / AUM_MIN) * SLIDER_STEPS);
const posToAum = (pos: number) => {
  const raw = AUM_MIN * (AUM_MAX / AUM_MIN) ** (pos / SLIDER_STEPS);
  const snap = raw < 20 ? 1 : raw < 100 ? 5 : raw < 500 ? 10 : raw < 1000 ? 25 : 50;
  return Math.min(AUM_MAX, Math.max(AUM_MIN, Math.round(raw / snap) * snap));
};

export function BusinessStep({ answers, update }: StepProps) {
  const toggle = (key: Answers['revenue'][number]) => update({ revenue: answers.revenue.includes(key) ? answers.revenue.filter(r => r !== key) : [...answers.revenue, key] });
  const pos = aumToPos(answers.aum);
  return (
    <motion.div className="ob-fields" variants={stagger(0.06)} initial="hidden" animate="show">
      <Item variants={fadeUp} className="ob-field">
        <div className="ob-slider-head"><span>Assets under management</span><motion.strong key={answers.aum} initial={{ y: -6, opacity: 0 }} animate={{ y: 0, opacity: 1 }} className="mono">{fmtAum(answers.aum)}</motion.strong></div>
        <input type="range" className="ob-range" min={0} max={SLIDER_STEPS} step={1} value={pos} style={{ '--fill': `${pos / SLIDER_STEPS * 100}%` } as React.CSSProperties} onChange={e => update({ aum: posToAum(Number(e.target.value)) })} aria-label="Assets under management" aria-valuetext={fmtAum(answers.aum)} />
        <div className="ob-range-ends" aria-hidden>{[1, 10, 100, 1000, 2000].map(m => <span key={m} style={{ left: `${aumToPos(m) / SLIDER_STEPS * 100}%` }}>{fmtAum(m)}</span>)}</div>
      </Item>
      <Field label="Number of client households">
        <div className="ob-stepper">
          <button type="button" onClick={() => update({ clients: Math.max(1, answers.clients - 10) })} aria-label="Ten fewer clients">−</button>
          <input inputMode="numeric" value={answers.clients} onChange={e => update({ clients: Math.max(0, Number(e.target.value.replace(/\D/g, '')) || 0) })} />
          <button type="button" onClick={() => update({ clients: answers.clients + 10 })} aria-label="Ten more clients">+</button>
        </div>
      </Field>
      <Item variants={fadeUp} className="ob-field">
        <span className="ob-label">How the practice is paid</span>
        <div className="ob-chips">
          {REVENUE_TYPES.map(r => { const on = answers.revenue.includes(r.key); return (
            <motion.button type="button" key={r.key} className={`ob-chip ${on ? 'on' : ''}`} onClick={() => toggle(r.key)} whileTap={{ scale: 0.95 }} aria-pressed={on}>
              <AnimatePresence initial={false}>{on && <motion.span initial={{ width: 0, opacity: 0 }} animate={{ width: 'auto', opacity: 1 }} exit={{ width: 0, opacity: 0 }} transition={spring} className="ob-chip-check"><Check size={13} /></motion.span>}</AnimatePresence>
              {r.label}
            </motion.button>
          ); })}
        </div>
        <small>Otter checks each payout statement against what these should have paid.</small>
      </Item>
    </motion.div>
  );
}

let memberSeq = 0;

export function TeamStep({ answers, update }: StepProps) {
  const set = (id: string, patch: Partial<Member>) => update({ team: answers.team.map(m => m.id === id ? { ...m, ...patch } : m) });
  const add = () => update({ team: [...answers.team, { id: `new-${Date.now()}-${memberSeq++}`, name: '', email: '', role: 'ops' }] });
  return (
    <motion.div className="ob-fields" variants={stagger(0.06)} initial="hidden" animate="show">
      <Item variants={fadeUp} className="ob-member owner">
        <span className="ob-avatar">{initials(answers.yourName)}</span>
        <div><strong>{answers.yourName || 'You'}</strong><small>{answers.email}</small></div>
        <span className="ob-role-tag">Owner · approves everything</span>
      </Item>
      <motion.ul className="ob-team" layout>
        <AnimatePresence initial={false}>
          {answers.team.map(m => (
            <motion.li key={m.id} layout initial={{ opacity: 0, y: 12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, x: -24, transition: { duration: 0.18 } }} transition={spring} className="ob-member">
              <span className="ob-avatar">{m.name ? initials(m.name) : <UserRound size={15} />}</span>
              <div className="ob-member-fields">
                <input value={m.name} onChange={e => set(m.id, { name: e.target.value })} placeholder="Name" aria-label="Teammate name" />
                <input type="email" value={m.email} onChange={e => set(m.id, { email: e.target.value })} placeholder="Email" aria-label="Teammate email" />
              </div>
              <div className="ob-roles" role="radiogroup" aria-label={`Role for ${m.name || 'teammate'}`}>
                {(Object.keys(ROLE_INFO) as TeamRole[]).map(role => (
                  <button type="button" key={role} role="radio" aria-checked={m.role === role} className={m.role === role ? 'on' : ''} onClick={() => set(m.id, { role })} title={ROLE_INFO[role].blurb}>
                    {m.role === role && <motion.span layoutId={`role-${m.id}`} className="ob-roles-pill" transition={spring} />}
                    <span>{ROLE_INFO[role].label}</span>
                  </button>
                ))}
              </div>
              <button type="button" className="ob-icon-btn" onClick={() => update({ team: answers.team.filter(x => x.id !== m.id) })} aria-label={`Remove ${m.name || 'teammate'}`}><Trash2 size={15} /></button>
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
      <Item variants={fadeUp}><button type="button" className="ob-add" onClick={add}><Plus size={15} />Add a teammate</button></Item>
      <Item variants={fadeUp} className="ob-note"><ShieldCheck size={16} />Nobody can approve a bill they uploaded. Partners approve anything over your limit.</Item>
    </motion.div>
  );
}

export function RulesStep({ answers, update }: StepProps) {
  return (
    <motion.div className="ob-fields" variants={stagger(0.07)} initial="hidden" animate="show">
      {STARTER_RULES.map(rule => { const on = answers.rules[rule.id]; return (
        <Item variants={fadeUp} key={rule.id}>
          <button type="button" role="switch" aria-checked={on} className={`ob-rule ${on ? 'on' : ''}`} onClick={() => update({ rules: { ...answers.rules, [rule.id]: !on } })}>
            <div><strong>{rule.title}</strong><small>{rule.detail}</small></div>
            <span className="ob-switch"><motion.span layout transition={spring} /></span>
          </button>
        </Item>
      ); })}
      <Item variants={fadeUp} className="ob-note"><ShieldCheck size={16} />You can change these or add your own later under Money out → Rules.</Item>
    </motion.div>
  );
}

const SAMPLE_FILES = ['Orion Software invoice.pdf', 'Seaport lease – October.pdf', 'LPL payout – September.pdf'];

export function DocumentsStep({ answers, update }: StepProps) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const addFiles = (names: string[]) => update({ files: [...answers.files, ...names.filter(n => !answers.files.includes(n))].slice(0, 6) });
  return (
    <motion.div className="ob-fields" variants={stagger(0.07)} initial="hidden" animate="show">
      <Item variants={fadeUp}>
        <motion.div className={`ob-drop ${over ? 'over' : ''}`} animate={{ scale: over ? 1.015 : 1 }} transition={spring}
          onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); addFiles(Array.from(e.dataTransfer.files).map(f => f.name)); }}
          onClick={() => input.current?.click()} role="button" tabIndex={0} onKeyDown={e => { if (e.key === ' ') { e.preventDefault(); input.current?.click(); } }}>
          <motion.span className="ob-drop-icon" animate={{ y: over ? -4 : [0, -4, 0] }} transition={over ? spring : { duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}><UploadCloud size={22} /></motion.span>
          <strong>Drop invoices, receipts and statements</strong>
          <small>or <u>browse files</u> · we&apos;ll import them right after you sign in</small>
          <input ref={input} type="file" multiple hidden onChange={e => addFiles(Array.from(e.target.files ?? []).map(f => f.name))} />
        </motion.div>
      </Item>
      {!answers.files.length && <Item variants={fadeUp}><button type="button" className="ob-add" onClick={() => addFiles(SAMPLE_FILES)}><FileText size={15} />Use sample documents</button></Item>}
      <motion.ul className="ob-files">
        <AnimatePresence initial={false}>
          {answers.files.map((f, i) => (
            <motion.li key={f} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0, transition: { ...spring, delay: i * 0.05 } }} exit={{ opacity: 0, scale: 0.96 }}>
              <FileText size={15} /><span>{f}</span><span className="ob-file-tag">Queued</span>
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
      <Item variants={fadeUp}>
        <button type="button" role="switch" aria-checked={answers.payoutsConnected} className={`ob-rule ${answers.payoutsConnected ? 'on' : ''}`} onClick={() => update({ payoutsConnected: !answers.payoutsConnected })}>
          <div><strong><Link2 size={15} /> Connect payout statements</strong><small>Monthly payouts arrive on their own and are matched to your fee schedule.</small></div>
          <span className="ob-switch"><motion.span layout transition={spring} /></span>
        </button>
      </Item>
    </motion.div>
  );
}

// "Setting up your books…": ticks each task off, then calls onDone.
export function SetupScreen({ onDone }: { onDone: () => void }) {
  const [done, setDone] = useState(0);
  const finish = useRef(onDone); finish.current = onDone;
  useEffect(() => {
    if (done >= SETUP_TASKS.length) { const t = setTimeout(() => finish.current(), 550); return () => clearTimeout(t); }
    const t = setTimeout(() => setDone(d => d + 1), done === 0 ? 700 : 850);
    return () => clearTimeout(t);
  }, [done]);
  return (
    <div className="ob-setup" role="status" aria-live="polite">
      <motion.div className="ob-orbit" animate={{ rotate: 360 }} transition={{ duration: 6, repeat: Infinity, ease: 'linear' }}><span /><span /><span /></motion.div>
      <motion.h2 variants={fadeUp} initial="hidden" animate="show">Setting up your books…</motion.h2>
      <ul>
        {SETUP_TASKS.map((task, i) => (
          <motion.li key={task} initial={{ opacity: 0, x: -10 }} animate={{ opacity: i <= done ? 1 : 0.35, x: 0 }} transition={{ ...spring, delay: i * 0.08 }} className={i < done ? 'done' : i === done ? 'active' : ''}>
            <span className="ob-tick">{i < done ? <motion.svg viewBox="0 0 16 16" width="12" height="12"><motion.path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.35 }} /></motion.svg> : i === done ? <span className="ob-spinner" /> : null}</span>
            {task}
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

export function ReadyScreen({ answers, onOpen, live }: { answers: Answers; onOpen: () => void; live: boolean }) {
  const first = answers.yourName.trim().split(/\s+/)[0] || 'there';
  const facts = [
    `${answers.team.length + 1} people`,
    `${Object.values(answers.rules).filter(Boolean).length} approval rules on`,
    answers.files.length ? `${answers.files.length} documents queued` : 'Ready for documents',
  ];
  return (
    <motion.div className="ob-ready" variants={stagger(0.09, 0.35)} initial="hidden" animate="show">
      <motion.div className="ob-check-big" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', stiffness: 220, damping: 14 }}>
        <svg viewBox="0 0 52 52" width="56" height="56"><motion.circle cx="26" cy="26" r="23" fill="none" stroke="currentColor" strokeWidth="2.5" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.6, ease: 'easeOut' }} /><motion.path d="M15 27l7 7 15-16" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.45, delay: 0.45, ease: 'easeOut' }} /></svg>
      </motion.div>
      <motion.h2 variants={fadeUp}>You&apos;re ready, {first}.</motion.h2>
      <motion.p variants={fadeUp}>{answers.practiceName || 'Your practice'} is set up on Otter.</motion.p>
      <motion.ul variants={fadeUp} className="ob-facts">{facts.map(f => <li key={f}><Check size={13} />{f}</li>)}</motion.ul>
      <motion.div variants={fadeUp}><motion.button type="button" className="button primary ob-cta" onClick={onOpen} whileHover={{ y: -1 }} whileTap={{ scale: 0.97 }} autoFocus>Open my workspace</motion.button></motion.div>
      {live && <motion.small variants={fadeUp} className="ob-fine">Next, sign in as {answers.email}.</motion.small>}
    </motion.div>
  );
}

function initials(name: string) { return name.trim().split(/\s+/).slice(0, 2).map(p => p[0]?.toUpperCase() ?? '').join('') || '?'; }
