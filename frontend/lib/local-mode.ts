export function validateLocalApi(baseUrl: string | undefined) {
  if (!baseUrl) throw new Error('Set NEXT_PUBLIC_API_URL=http://localhost:8787 for local API mode.');
  const url = new URL(baseUrl);
  if (!['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || !['http:', 'https:'].includes(url.protocol)) {
    throw new Error('Local API mode requires a loopback URL. Use Cognito for hosted APIs.');
  }
  return url.toString().replace(/\/$/, '');
}
