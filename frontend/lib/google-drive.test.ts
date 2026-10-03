import { test } from 'node:test';
import assert from 'node:assert/strict';
import { authorizeDrive, downloadDriveFile, driveDownloadPlan, DriveAuthExpiredError, DRIVE_SCOPE, pickDriveFiles } from './google-drive';
import { MAX_DOCUMENT_BYTES } from './upload-file';
import { api } from './api';

test('supported binary formats preserve their names and download using alt=media', () => {
  for (const mimeType of ['application/pdf', 'image/png', 'image/jpeg']) {
    const plan = driveDownloadPlan({ id: 'a/b', name: 'Original name', mimeType, size: '42' });
    assert.equal(plan.name, 'Original name'); assert.equal(plan.type, mimeType);
    assert.match(plan.url, /a%2Fb\?alt=media/);
  }
});
test('Docs, Sheets and Slides use PDF export; PDF suffix is not duplicated', () => {
  for (const type of ['document', 'spreadsheet', 'presentation']) {
    const plan = driveDownloadPlan({ id: 'native', name: 'Book', mimeType: `application/vnd.google-apps.${type}` });
    assert.equal(plan.name, 'Book.pdf'); assert.equal(plan.type, 'application/pdf');
    assert.match(plan.url, /\/export\?mimeType=application%2Fpdf/);
  }
  assert.equal(driveDownloadPlan({ id: '1', name: 'Book.PDF', mimeType: 'application/vnd.google-apps.document' }).name, 'Book.PDF');
});
test('unsupported formats, disabled downloads and oversized binaries fail before download', () => {
  for (const mimeType of ['text/plain', 'text/csv', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.google-apps.folder', 'application/vnd.google-apps.shortcut']) {
    assert.throws(() => driveDownloadPlan({ id: '1', name: 'Book', mimeType }), /Unsupported file type/);
  }
  assert.throws(() => driveDownloadPlan({ id: '1', name: 'Book', mimeType: 'application/pdf', size: String(MAX_DOCUMENT_BYTES + 1) }), /20 MB/);
  assert.throws(() => driveDownloadPlan({ id: '1', name: 'Book', mimeType: 'application/pdf', capabilities: { canDownload: false } }), /disabled downloading/);
});
test('downloads preserve metadata and create Files accepted by the existing upload flow', async t => {
  const source = { id: '1', name: 'drive-receipt.pdf', mimeType: 'application/pdf', size: '6' };
  const calls: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string, options: RequestInit) => {
    calls.push(url); assert.equal((options.headers as Record<string, string>).Authorization, 'Bearer temporary-test-token');
    return url.includes('fields=') ? Response.json(source) : new Response('sample');
  });
  const { file, source: metadata } = await downloadDriveFile('1', { token: 'temporary-test-token', expiresAt: Date.now() + 60000 }, new AbortController().signal);
  assert.deepEqual(metadata, source); assert.equal(file.name, source.name); assert.equal(file.type, source.mimeType); assert.equal(file.size, 6);
  const doc = await api.upload(file, () => {}); assert.equal(doc.filename, source.name);
  assert.equal(calls.length, 2);
});
test('expired tokens and HTTP 401 require reconnection', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 401 }));
  const signal = new AbortController().signal;
  await assert.rejects(downloadDriveFile('1', { token: 'test', expiresAt: 0 }, signal), DriveAuthExpiredError);
  assert.equal(fetch.mock.callCount(), 0);
  await assert.rejects(downloadDriveFile('1', { token: 'test', expiresAt: Date.now() + 60000 }, signal), DriveAuthExpiredError);
});
test('native files are exported and returned as PDF Files', async t => {
  const urls: string[] = [];
  t.mock.method(globalThis, 'fetch', async (url: string) => {
    urls.push(url);
    return url.includes('fields=') ? Response.json({ id: '1', name: 'Statement', mimeType: 'application/vnd.google-apps.spreadsheet' }) : new Response('pdf');
  });
  const { file } = await downloadDriveFile('1', { token: 'test', expiresAt: Date.now() + 60000 }, new AbortController().signal);
  assert.equal(file.name, 'Statement.pdf'); assert.equal(file.type, 'application/pdf'); assert.match(urls[1], /\/export\?/);
});
test('stream size is bounded even without Content-Length; denied downloads are actionable', async t => {
  t.mock.method(globalThis, 'fetch', async (url: string) => url.includes('fields=') ? Response.json({ id: '1', name: 'Big', mimeType: 'application/pdf' }) : new Response(new Uint8Array(MAX_DOCUMENT_BYTES + 1)));
  const auth = { token: 'test', expiresAt: Date.now() + 60000 }; const signal = new AbortController().signal;
  await assert.rejects(downloadDriveFile('1', auth, signal), /20 MB/);
  t.mock.restoreAll();
  t.mock.method(globalThis, 'fetch', async () => new Response('', { status: 403 }));
  await assert.rejects(downloadDriveFile('1', auth, signal), /Google denied/);
});
test('unmounted or aborted imports stop before fetching', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => Response.json({}));
  const abort = new AbortController(); abort.abort();
  await assert.rejects(downloadDriveFile('1', { token: 'test', expiresAt: Date.now() + 60000 }, abort.signal), /abort/i);
  assert.equal(fetch.mock.callCount(), 0);
});

test('OAuth requests only per-file access and handles denial, missing scope and popup cancellation', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'window', previous); else Reflect.deleteProperty(globalThis, 'window'); });
  let outcome = 'success';
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { google: { accounts: { oauth2: {
    initTokenClient(config: { scope: string; include_granted_scopes: boolean; callback: (response: object) => void; error_callback: (error: object) => void }) {
      assert.equal(config.scope, DRIVE_SCOPE); assert.equal(config.include_granted_scopes, false);
      return { requestAccessToken() {
        if (outcome === 'closed') config.error_callback({ type: 'popup_closed' });
        else if (outcome === 'denied') config.callback({ error: 'access_denied' });
        else config.callback({ access_token: 'test', expires_in: 3600, scope: outcome === 'success' ? DRIVE_SCOPE : '' });
      } };
    },
  } } } } });
  assert.equal((await authorizeDrive()).token, 'test');
  outcome = 'denied'; await assert.rejects(authorizeDrive(), /denied/);
  outcome = 'missing'; await assert.rejects(authorizeDrive(), /permission/);
  outcome = 'closed'; await assert.rejects(authorizeDrive(), /canceled/);
});

test('Picker enables multi-selection, returns deduplicated IDs and disposes on cancel or abort', async t => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'window');
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'window', previous); else Reflect.deleteProperty(globalThis, 'window'); });
  let callback: (data: { action: string; docs?: { id: string }[] }) => void = () => {};
  let disposed = 0; let feature = ''; let origin = '';
  class DocsView {
    setIncludeFolders() { return this; } setSelectFolderEnabled() { return this; } setMode() { return this; }
  }
  class PickerBuilder {
    addView() { return this; } setOAuthToken() { return this; } setDeveloperKey() { return this; } setAppId() { return this; }
    setOrigin(value: string) { origin = value; return this; }
    enableFeature(value: string) { feature = value; return this; }
    setCallback(value: typeof callback) { callback = value; return this; }
    build() { return { setVisible() {}, dispose() { disposed++; } }; }
  }
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { origin: 'http://localhost:3000' }, google: { picker: {
    DocsView, PickerBuilder, ViewId: { DOCS: 'docs' }, DocsViewMode: { LIST: 'list' }, Feature: { MULTISELECT_ENABLED: 'multi' }, Action: { PICKED: 'picked', CANCEL: 'cancel' },
  } } } });
  const auth = { token: 'test', expiresAt: Date.now() + 60000 };
  const first = pickDriveFiles(auth, new AbortController().signal);
  callback({ action: 'picked', docs: [{ id: '1' }, { id: '2' }, { id: '1' }] });
  assert.deepEqual(await first, ['1', '2']); assert.equal(feature, 'multi'); assert.equal(origin, 'http://localhost:3000');
  const second = pickDriveFiles(auth, new AbortController().signal); callback({ action: 'cancel' });
  assert.equal(await second, null);
  const abort = new AbortController(); const third = pickDriveFiles(auth, abort.signal); abort.abort();
  await assert.rejects(third, /canceled/); assert.equal(disposed, 3);
});
