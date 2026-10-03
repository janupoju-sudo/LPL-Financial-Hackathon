# Google Drive import: setup and testing

## Existing architecture and integration

The Documents upload area is `frontend/components/workspace.tsx` (`Upload`). Local selections and drops are browser `File` objects, passed to `api.upload` in `frontend/lib/api.ts`. The document uploader accepts PDF, PNG and JPEG, up to 20 MiB. In live mode it obtains `/documents/upload-url`, PUTs the file to the presigned S3 URL, then polls the existing document endpoint for extraction completion. The S3 ingestion pipeline uses Textract. The library and detail views consume the existing `Document` records. Mock mode retains the file as a blob preview and simulates extraction; data resets on reload. Local API mode has no upload endpoint, so both upload buttons are disabled.

Drive integration lives in `frontend/components/google-drive-import.tsx` and `frontend/lib/google-drive.ts`. Google Identity Services obtains an OAuth 2.0 access token using only `https://www.googleapis.com/auth/drive.file`. The official Picker lets users browse folders and select multiple files without granting the application access to their entire Drive. After selection, Drive v3 retrieves metadata, downloads binary content using `files.get` with `alt=media`, or exports Docs, Sheets and Slides using `files.export` to PDF. The resulting browser `File` goes through the same `processFile` / `api.upload` path as a local drop, including validation, storage, extraction, library refresh and preview.

Filename, MIME type and actual byte size are preserved on the `File`; Workspace exports add `.pdf`. Original Drive metadata (ID, original name, MIME type, size when available) is returned by the download helper for the import operation. Drive source IDs are not persisted in document records because the existing processing system does not need ongoing Drive access. Tokens are held only in the running import operation, never logged, stored in local/session storage, or sent to the application backend. Each new import obtains authorization again; no client secret or refresh token is needed.

TXT, CSV, Office files, other image formats, shortcuts and other Google native formats are explicitly rejected by this document importer because the existing document pipeline does not support them. CSV already has a separate live transaction-import flow, which this change leaves intact. Convert unsupported documents to PDF before importing. Sheets are exported as PDF to preserve the existing document processing contract, not sent to the CSV transaction importer. Google's Workspace export endpoint has a 10 MB export limit; the application additionally enforces its 20 MiB upload limit, including during streamed downloads. See [Drive downloads and exports](https://developers.google.com/workspace/drive/api/guides/manage-downloads).

## Environment variables

Set these in `frontend/.env.local` locally, and in the frontend hosting build environment for production:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Web application OAuth client ID, ending in `.apps.googleusercontent.com` |
| `NEXT_PUBLIC_GOOGLE_API_KEY` | Restricted browser API key from the same Cloud project |
| `NEXT_PUBLIC_GOOGLE_APP_ID` | Numeric Cloud project number from that same project; not the string project ID |

Both example environment files contain placeholders. Replace them with real values; do not put real credentials in the examples. `.env.local` stays ignored. These three values are necessarily public browser configuration. Restrict the API key; never add an OAuth client secret to `NEXT_PUBLIC_*` variables. Next embeds these variables at build time, so restart development or rebuild production after changes.

Existing mode configuration still applies: use `NEXT_PUBLIC_USE_MOCKS=true` and `NEXT_PUBLIC_LOCAL_API=false` for real Drive downloads with simulated application processing. For actual S3 storage/extraction use the existing live backend, Cognito and API variables documented in `frontend/README.md`, with both mode flags false. Google sign-in grants Drive access; it does not replace application sign-in.

## Google Cloud setup

1. Open [Google Cloud Console](https://console.cloud.google.com/), create or select one project, and use that project for all three credentials. Record the numeric **Project number** from the project dashboard.
2. Under **APIs & Services → Library**, enable exactly **Google Drive API** and **Google Picker API**. The Docs, Sheets and Slides APIs are not needed; their files are exported through Drive.
3. Open **Google Auth Platform** and configure **Branding**: app name, support email and developer contact. For production, supply your application homepage, privacy policy, and required verified domains.
4. Under **Audience**, choose **Internal** only if all users belong to your eligible Workspace organization; otherwise choose **External**. During external testing, keep the app in Testing and add the Google accounts you will use under **Test users**.
5. Under **Data Access → Add or remove scopes**, add only `https://www.googleapis.com/auth/drive.file`. This is the recommended per-file scope; do not add `drive`, `drive.readonly`, or unrelated account scopes. Although Google's per-file scope permits modification of selected files, this implementation only reads them. See [Google's scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
6. Under **Google Auth Platform → Clients → Create client**, select **Web application** and name it (for example, Ledgerline development).
7. Set **Authorized JavaScript origins** to `http://localhost:3000`. This URL is documented in both project READMEs, and `frontend/package.json` uses `next dev` without a custom port. Do not include `/documents` or a wildcard in an OAuth origin. If you actually run on a different origin or port, add that exact origin separately.
8. Leave **Authorized redirect URIs** empty for this integration. It uses the browser popup token flow with a JavaScript callback, not a server OAuth callback route. No new callback path exists. Copy the client ID into `NEXT_PUBLIC_GOOGLE_CLIENT_ID`; no client secret is used.
9. Open **APIs & Services → Credentials → Create credentials → API key**, then edit the key. Under **Application restrictions**, choose **Websites (HTTP referrers)** and add `http://localhost:3000/*` and `https://docs.google.com/*`. Google's official Picker instructions require the latter because the Picker runs in a Google-hosted iframe.
10. Under **API restrictions**, choose **Restrict key** and select **Google Picker API** and **Google Drive API**. Save and put the key into `NEXT_PUBLIC_GOOGLE_API_KEY`. Put the numeric project number into `NEXT_PUBLIC_GOOGLE_APP_ID`.
11. Restart the frontend after changing `.env.local`. Configuration propagation in Google Cloud can take a few minutes. For SDK loading, authorization and key restrictions, see [Google's official Picker setup](https://developers.google.com/workspace/drive/picker/guides/web-picker) and [OAuth token flow](https://developers.google.com/identity/oauth2/web/guides/use-token-model).

## Before production deployment

Use production credentials (preferably a separate project/key/client from development) and set all three variables in the Amplify build environment before building. Add your actual HTTPS application origin to the OAuth client's JavaScript origins. Restrict the production key to `https://YOUR-ACTUAL-DOMAIN/*` and `https://docs.google.com/*`; remove localhost from that production key. No production domain is assumed here because the repository does not establish one for this deployment.

Complete consent branding, verified domains, privacy policy and Audience publishing/verification requirements shown by Google for your app. Ensure intended users can authorize the app outside the test-user list. Keep `drive.file` as the only requested scope. If a hosting CSP is introduced, allow Google's Identity Services/API loader scripts, authorization resources, the Picker iframe, and Drive API connections. Deploy and verify the existing upload backend as usual; no new backend endpoint or Google secret is needed.

## Automated verification

From `frontend`, run these sequentially (the build regenerates Next types):

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run typecheck
```

The Drive tests cover normal download URLs, native PDF exports, original names and metadata, reusing `api.upload`, unsupported formats, permissions, oversize streams, authorization expiry and aborts. Unit tests use mocked Google responses; they do not validate real Cloud credentials or a browser consent session.

## Manual browser testing

1. **Start:** set the three Google variables in `.env.local`; set `NEXT_PUBLIC_USE_MOCKS=true` and `NEXT_PUBLIC_LOCAL_API=false` for an isolated application test. Run `npm.cmd run dev` in `frontend`. Open `http://localhost:3000/documents` and expand the upload area with **Upload** if collapsed. Allow sign-in popups. Use a configured test-user Google account.
2. **Authentication:** click **Import from Google Drive**. Expect **Connecting to Google**, account selection/consent if needed, and only the per-file Drive permission. If clicked before the SDK is ready, it loads the SDK and asks for a second click to preserve browser popup authorization. Complete Google consent. For a first-consent test, remove this app's grant in your Google Account connections before repeating.
3. **Opening Picker:** after authentication expect **Opening Google Drive**, followed by Google's official Picker. Browse folders; folders themselves cannot be selected. No additional application login is requested by the Picker.
4. **Normal file:** select a PDF, PNG or JPG under 20 MiB and click Select. Expect a selection/import status, the usual upload/extraction progress, completion, a library entry with the original filename, and a working preview. Mock extraction explicitly uses sample fields. Repeat with live mode to verify S3 and Textract processing.
5. **Google Doc:** create a short Google Doc, select it and verify a `.pdf` document/preview. Repeat with a Sheet and Slide deck. Confirm the PDF output rather than a zero-byte native file. Large native exports may fail at Google's 10 MB limit.
6. **Multiple files:** select two supported files (including one native Doc) using the Picker's multi-selection controls and click Select. Expect sequential `Importing 1 of 2` / `2 of 2`, both library entries, and a completion count. Close document detail if it opens during processing; imports continue. Repeat with one unsupported TXT file plus one PDF: the PDF should still import and the summary should report partial failure. Successful imports are not rolled back.
7. **Cancel Picker:** click Import and then Cancel in the Picker. Expect **Google Drive picker canceled. No files imported.** Existing documents remain unchanged and the upload controls become available again.
8. **Authorization failure:** revoke the app grant in your Google Account, start an import, then deny consent or close the Google popup. Expect the authorization-denied/canceled message and an enabled retry button. A popup blocked by the browser should suggest allowing popups. A non-test user on an external Testing app can also produce an authorization failure.
9. **Expired authorization:** authorize and leave the Picker open until the access token expires, then select a file. Expect a message that authorization expired and instructs you to reconnect; the button should become available. For a faster deterministic test, in browser developer tools set a breakpoint in `downloadDriveFile` before its expiry check and change `auth.expiresAt` to `0`, then resume. Alternatively intercept a request to `www.googleapis.com/drive/v3/files/...` in a browser testing proxy and return HTTP 401. The next import should obtain a fresh token. If some files already imported, they remain in the library; select only the remaining files on retry.
10. **Other failures:** select an unsupported Office/TXT/CSV file, an oversized PDF, or a file whose owner disallows downloads. Expect an actionable error and no processing of that failed file. Block Google script loading and verify the retry state. Navigate away while importing and verify the Picker/download is disposed or aborted.
11. **Token handling:** inspect browser storage and application backend requests: no Google token should be persisted or forwarded to the backend. Drive requests use the Authorization header; never copy or log its value. Local file selection and drag/drop should still follow their original behavior.

## Files changed for this feature

Created: `frontend/components/google-drive-import.tsx`, `frontend/lib/google-drive.ts`, `frontend/lib/google-drive.test.ts`, `frontend/lib/upload-file.ts`, and this guide.

Modified: `.gitignore`, `frontend/.env.example`, `frontend/.env.live.example`, `frontend/README.md`, `frontend/package.json`, `frontend/app/globals.css`, `frontend/components/workspace.tsx`, `frontend/lib/api.ts`. The ignore-file correction ensures the two placeholder examples are not masked by its later `.env.*` rule.
