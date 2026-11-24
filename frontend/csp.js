/**
 * Content-Security-Policy for the web app.
 *
 * Production pages emit no inline executable script (Next's data block is type="application/json",
 * which is not executed), so scripts are allowed from the app itself only: no nonce, no hash, no
 * unsafe-inline, no eval. Styles keep 'unsafe-inline' because React and Next set style attributes.
 * The one foreign origin is the API's, taken from NEXT_PUBLIC_API_BASE_URL when the app is built.
 *
 * Development needs eval and a websocket for hot reload, and only there.
 */
const DEFAULT_API = "http://localhost:8000";

function apiOrigin(apiBase) {
  try {
    return new URL(apiBase || DEFAULT_API).origin;
  } catch {
    return DEFAULT_API;
  }
}

function contentSecurityPolicy({ apiBase, dev }) {
  return [
    "default-src 'self'",
    `script-src 'self'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src 'self' ${apiOrigin(apiBase)}${dev ? " ws:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

module.exports = { contentSecurityPolicy };
