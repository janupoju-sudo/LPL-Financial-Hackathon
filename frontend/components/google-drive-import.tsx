'use client';

import { useEffect, useRef, useState } from 'react';
import { FolderOpen, LoaderCircle } from 'lucide-react';
import { Button } from './ui/button';
import { authorizeDrive, downloadDriveFile, DriveAuthExpiredError, driveConfigured, pickDriveFiles, prepareDrive } from '@/lib/google-drive';

export function GoogleDriveImport({ disabled, onBusy, upload, notify }: {
  disabled: boolean; onBusy: (busy: boolean) => void;
  upload: (file: File, progress: (status: string) => void, signal: AbortSignal) => Promise<void>;
  notify: (message: string) => void;
}) {
  const [ready, setReady] = useState(false); const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(''); const [failed, setFailed] = useState(false);
  const controller = useRef<AbortController | null>(null); const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    if (driveConfigured) void prepareDrive().then(() => { if (mounted.current) setReady(true); }).catch(() => {
      if (mounted.current) { setFailed(true); setStatus('Google could not load. Click Import from Google Drive to retry.'); }
    });
    return () => { mounted.current = false; controller.current?.abort(); };
  }, []);
  const start = async () => {
    if (busy || disabled) return;
    if (!driveConfigured) { setFailed(true); setStatus('Google Drive import is not configured. See the Google Drive setup guide.'); return; }
    // SDK loading is done before the OAuth click so authorization remains a user gesture.
    if (!ready) {
      setBusy(true); onBusy(true); setFailed(false); setStatus('Connecting to Google');
      try { await prepareDrive(); if (mounted.current) { setReady(true); setStatus('Google is ready. Click Import from Google Drive to connect.'); } }
      catch { if (mounted.current) { setFailed(true); setStatus('Google could not load. Check your connection and browser blockers, then retry.'); } }
      finally { if (mounted.current) { setBusy(false); onBusy(false); } }
      return;
    }
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); onBusy(true); setFailed(false); setStatus('Connecting to Google');
    let imported = 0; const errors: string[] = [];
    try {
      const auth = await authorizeDrive();
      abort.signal.throwIfAborted();
      setStatus('Opening Google Drive');
      const ids = await pickDriveFiles(auth, abort.signal);
      if (!ids?.length) { setStatus('Google Drive picker canceled. No files imported.'); return; }
      setStatus(`${ids.length} file${ids.length === 1 ? '' : 's'} selected`);
      for (const [index, id] of ids.entries()) {
        try {
          setStatus(`${ids.length} file${ids.length === 1 ? '' : 's'} selected. Importing ${index + 1} of ${ids.length}`);
          const { file } = await downloadDriveFile(id, auth, abort.signal);
          await upload(file, progress => { if (mounted.current) setStatus(`Importing ${index + 1} of ${ids.length}: ${file.name} — ${progress}`); }, abort.signal);
          imported++;
        } catch (error) {
          abort.signal.throwIfAborted();
          errors.push(`File ${index + 1}: ${error instanceof Error ? error.message : 'Import failed.'}`);
          if (error instanceof DriveAuthExpiredError) break;
        }
      }
      setFailed(errors.length > 0);
      const summary = errors.length ? `Import failed for some files. ${imported} of ${ids.length} imported. ${errors.join(' ')}` : `Import complete. ${imported} file${imported === 1 ? '' : 's'} imported.${process.env.NEXT_PUBLIC_USE_MOCKS !== 'false' ? ' Demo extraction uses sample fields.' : ''}`;
      setStatus(summary); notify(summary);
    } catch (error) {
      if (!abort.signal.aborted) { setFailed(true); setStatus(error instanceof Error ? error.message : 'Google Drive import failed. Please try again.'); }
    } finally {
      // auth is scoped to this operation and discarded; no local/session storage or refresh token.
      if (mounted.current) { setBusy(false); onBusy(false); }
      controller.current = null;
    }
  };
  return <div className="drive-import">
    <Button variant="outline" disabled={disabled || busy} onClick={() => void start()}>{busy ? <LoaderCircle className="spin" size={16} /> : <FolderOpen size={16} />} Import from Google Drive</Button>
    {status && <p className={failed ? 'text-red' : 'muted'} role={failed ? 'alert' : 'status'} aria-live="polite">{status}</p>}
  </div>;
}
