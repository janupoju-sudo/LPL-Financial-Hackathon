import { MAX_DOCUMENT_BYTES, validateDocumentFile } from './upload-file';

export const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file';
export const driveConfigured = Boolean(process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID && process.env.NEXT_PUBLIC_GOOGLE_API_KEY && process.env.NEXT_PUBLIC_GOOGLE_APP_ID);
const WORKSPACE_TYPES = ['application/vnd.google-apps.document', 'application/vnd.google-apps.spreadsheet', 'application/vnd.google-apps.presentation'];
export interface DriveMetadata { id: string; name: string; mimeType: string; size?: string; modifiedTime?: string; capabilities?: { canDownload?: boolean }; }
export class DriveAuthExpiredError extends Error {
  constructor() { super('Google authorization expired. Click Import from Google Drive to reconnect and select the remaining files.'); }
}

// Only the SDK surface used here is described; no credentials or tokens are persisted.
interface TokenResponse { access_token?: string; expires_in: number; scope?: string; error?: string; }
interface PickerResult { action: string; docs?: { id: string }[]; }
interface Picker { setVisible(visible: boolean): void; dispose(): void; }
interface DocsView { setIncludeFolders(value: boolean): DocsView; setSelectFolderEnabled(value: boolean): DocsView; setMode(value: string): DocsView; }
interface PickerBuilder {
  addView(view: DocsView): PickerBuilder; setOAuthToken(token: string): PickerBuilder;
  setDeveloperKey(key: string): PickerBuilder; setAppId(id: string): PickerBuilder;
  setOrigin(origin: string): PickerBuilder; enableFeature(feature: string): PickerBuilder;
  setCallback(callback: (data: PickerResult) => void): PickerBuilder; build(): Picker;
}
interface GoogleSdk {
  accounts: { oauth2: { initTokenClient(config: {
    client_id: string; scope: string; include_granted_scopes: boolean;
    callback: (response: TokenResponse) => void;
    error_callback: (error: { type: string }) => void;
  }): { requestAccessToken(options: { prompt: string }): void }; } };
  picker: { DocsView: new (id: string) => DocsView; ViewId: { DOCS: string }; DocsViewMode: { LIST: string };
    PickerBuilder: new () => PickerBuilder; Feature: { MULTISELECT_ENABLED: string }; Action: { PICKED: string; CANCEL: string }; };
}
declare global {
  interface Window { google?: GoogleSdk; gapi?: { load(name: string, options: { callback: () => void; onerror: () => void; timeout: number; ontimeout: () => void }): void }; }
}
let sdkPromise: Promise<void> | undefined;
function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    const timer = setTimeout(() => { script.remove(); reject(new Error('Google could not load. Check your connection and try again.')); }, 20000);
    script.src = src; script.async = true;
    script.onload = () => { clearTimeout(timer); resolve(); };
    script.onerror = () => { clearTimeout(timer); script.remove(); reject(new Error('Google could not load. Check your connection and browser blockers.')); };
    document.head.appendChild(script);
  });
}
export function prepareDrive(): Promise<void> {
  if (!sdkPromise) sdkPromise = Promise.all([
    window.google?.accounts ? Promise.resolve() : loadScript('https://accounts.google.com/gsi/client'),
    window.gapi ? Promise.resolve() : loadScript('https://apis.google.com/js/api.js'),
  ]).then(() => new Promise<void>((resolve, reject) => {
    window.gapi!.load('picker', { callback: resolve, onerror: () => reject(new Error('Google Drive Picker could not load.')), timeout: 20000, ontimeout: () => reject(new Error('Google Drive Picker timed out.')) });
  })).catch(error => { sdkPromise = undefined; throw error; });
  return sdkPromise;
}

export interface DriveAuthorization { token: string; expiresAt: number; }
// Call synchronously from a user click after SDK loading to avoid popup blockers.
export function authorizeDrive(): Promise<DriveAuthorization> {
  return new Promise((resolve, reject) => {
    window.google!.accounts.oauth2.initTokenClient({
      client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID!, scope: DRIVE_SCOPE, include_granted_scopes: false,
      callback: response => {
        if (response.error || !response.access_token || !response.scope?.split(' ').includes(DRIVE_SCOPE)) {
          reject(new Error('Google authorization denied or the required file permission was not granted. Please try again.')); return;
        }
        resolve({ token: response.access_token, expiresAt: Date.now() + response.expires_in * 1000 });
      },
      error_callback: error => reject(new Error(error.type === 'popup_closed' ? 'Google authorization canceled.' : 'Google sign-in could not open. Allow popups and try again.')),
    }).requestAccessToken({ prompt: '' });
  });
}

export function pickDriveFiles(auth: DriveAuthorization, signal: AbortSignal): Promise<string[] | null> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const sdk = window.google!.picker;
    let picker: Picker;
    const finish = (ids: string[] | null) => { signal.removeEventListener('abort', cancel); picker.dispose(); resolve(ids); };
    const cancel = () => { picker.dispose(); reject(new DOMException('Import canceled', 'AbortError')); };
    picker = new sdk.PickerBuilder()
      .addView(new sdk.DocsView(sdk.ViewId.DOCS).setIncludeFolders(true).setSelectFolderEnabled(false).setMode(sdk.DocsViewMode.LIST))
      .setOAuthToken(auth.token).setDeveloperKey(process.env.NEXT_PUBLIC_GOOGLE_API_KEY!)
      .setAppId(process.env.NEXT_PUBLIC_GOOGLE_APP_ID!).setOrigin(window.location.origin)
      .enableFeature(sdk.Feature.MULTISELECT_ENABLED)
      .setCallback(data => {
        if (data.action === sdk.Action.CANCEL) finish(null);
        if (data.action === sdk.Action.PICKED) finish([...new Set((data.docs ?? []).map(doc => doc.id))]);
      }).build();
    signal.addEventListener('abort', cancel, { once: true });
    picker.setVisible(true);
  });
}

export function driveDownloadPlan(metadata: DriveMetadata) {
  const exportPdf = WORKSPACE_TYPES.includes(metadata.mimeType);
  const type = exportPdf ? 'application/pdf' : metadata.mimeType;
  validateDocumentFile({ type, size: exportPdf ? 0 : Number(metadata.size ?? 0) });
  if (metadata.capabilities?.canDownload === false) throw new Error('The owner has disabled downloading this file.');
  const base = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(metadata.id)}`;
  return { url: exportPdf ? `${base}/export?mimeType=application%2Fpdf` : `${base}?alt=media&supportsAllDrives=true`,
    name: exportPdf && !metadata.name.toLowerCase().endsWith('.pdf') ? `${metadata.name}.pdf` : metadata.name, type };
}

export async function downloadDriveFile(id: string, auth: DriveAuthorization, signal: AbortSignal): Promise<{ file: File; source: DriveMetadata }> {
  const get = async (url: string) => {
    signal.throwIfAborted();
    if (Date.now() >= auth.expiresAt - 5000) throw new DriveAuthExpiredError();
    const response = await fetch(url, { headers: { Authorization: `Bearer ${auth.token}` }, signal, credentials: 'omit', redirect: 'error' });
    if (response.status === 401) throw new DriveAuthExpiredError();
    if (!response.ok) throw new Error(response.status === 403 ? 'Google denied this download. Check file permissions, API configuration, or the Google Workspace export size limit (10 MB).' : `Google Drive download failed (${response.status}). Please try again.`);
    return response;
  };
  const source = await (await get(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(id)}?fields=id,name,mimeType,size,modifiedTime,capabilities(canDownload)&supportsAllDrives=true`)).json() as DriveMetadata;
  const plan = driveDownloadPlan(source);
  const response = await get(plan.url);
  // Bound memory usage even when Drive omits Content-Length, notably for exports.
  if (Number(response.headers.get('content-length') ?? 0) > MAX_DOCUMENT_BYTES) { await response.body?.cancel(); throw new Error('Files must be smaller than 20 MB.'); }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Google Drive returned an empty response.');
  const chunks: ArrayBuffer[] = []; let size = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_DOCUMENT_BYTES) { await reader.cancel(); throw new Error('Files must be smaller than 20 MB.'); }
    chunks.push(value.slice().buffer as ArrayBuffer);
  }
  const file = new File(chunks, plan.name, { type: plan.type, lastModified: source.modifiedTime ? Date.parse(source.modifiedTime) : Date.now() });
  validateDocumentFile(file);
  return { file, source };
}
