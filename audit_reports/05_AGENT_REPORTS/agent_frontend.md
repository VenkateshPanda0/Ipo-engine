# Frontend security / usability / accessibility audit (agent_frontend)

Branch audit/remediation-2026-11. Date 2026-11-27. Scope: /home/user/ipo-due-diligence-engine/frontend (Next.js 15, pages router) and the static demo in /site.
Tracked files were not modified by this agent. `git status` at the end showed changes to src/ipo_engine/screening/*accounts*.py and a test file; those are not mine (another agent). A production `next build` wrote only to the git-ignored frontend/.next.

## Method
- Static review of frontend/src, csp.js, next.config.js, site/app.js.
- `npm audit --omit=dev`, `npm run typecheck`, `npm test`, lockfile licence scan (all run).
- Production build (`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 next build`, `next start :3000`), API via `uv run ipo serve` (default local mode, no auth). Browser probes with Playwright/Chromium from /tmp/agent_fe (probe.js, site.js, rules.js): response headers, axe-core (wcag2a/2aa/21aa) on 14 routes in light and dark at 1366px, overflow at 320px (light and dark), page errors, mocked-API hostile data (javascript: link, HTML in title, external link), `next=` handling.
- Not run: `npm run e2e` (needs the full workflow setup), lint (no lint script in package.json), CSRF behaviour against an accounts-mode API.

## Check results
| Check | Result |
|---|---|
| dangerouslySetInnerHTML / innerHTML / document.write / eval in frontend/src and site/ | Not Found (grep). Only mention of `new Function` is a comment in src/lib/zod.ts. |
| DOM XSS via API text | Not Found. Mocked notification title `<img src=x onerror=alert(1)>` rendered as text, no element injected, no dialog. Static demo with hostile `issuer` text: no `<img>` injected, no dialog. |
| javascript: URLs from API data (notifications link, onboarding link, rule source_url, rules s.url, demo `source`) | Not exploitable. Mocked `link: "javascript:alert(document.domain)"` was rewritten by React 19 to `javascript:throw new Error('React has blocked a javascript: URL...')`, click ran nothing, no dialog. Demo: `safeUrl` only allows https. No app-side validation exists (see F3). |
| Markdown rendering | Not Found (no markdown renderer). |
| Token storage | Confirmed design: API key in sessionStorage (src/lib/auth.ts), session in cookie (credentials include). Not in URLs. Any XSS would expose the key (sessionStorage is script-readable), but no XSS found. See F5. |
| CSP | Confirmed present and strong in prod: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self' <api>; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. Plus nosniff, Referrer-Policy no-referrer, X-Frame-Options DENY, Permissions-Policy. No inline executable script in the prerendered /login HTML (only `application/json` data block). Weakness: `style-src 'unsafe-inline'` (accepted in csp.js comment). The static demo (site/index.html) has no CSP meta tag (F6). |
| Open redirects | Not Found for `?next=`. `safeNext` (src/pages/login.tsx:10) rejects `//x`, `\`, absolute and `javascript:` values. The probe that reads the Google button did not find the button in local mode (no providers), so the output of `googleLoginUrl(next)` was not verified in the browser; safeNext logic is covered by reading the code only. Server-supplied `link` fields: see F3. `/shared/[token]` redirect uses encodeURIComponent on the token and a fixed base; Not Found. |
| CSRF header handling (src/lib/api.ts:70-110) | Reviewed, not exercised. Token fetched from /auth/csrf, sent as X-CSRF-Token on non-safe methods when no API key, one retry on 403. Looks correct. Local-mode /auth/csrf returns 403 "Sign in with a browser session" and the client tolerates it. Inconclusive against an accounts-mode API. |
| React Query races / double submit / unmount | Inconclusive (not tested dynamically; limited by tool budget). |
| Unhandled promise rejections / page errors | One confirmed: F1. Other routes produced no page errors (CORS noise only appeared in my first run because I used 127.0.0.1 as the page origin; with localhost there were none). |
| Error / loading / empty states | Partially checked: with API unreachable the routes still render a shell with no page error. Not exhaustive. |
| axe-core, 14 routes, light+dark @1366 | Not Found (0 violations on every route). 320px light: 1 violation on /rules (F2). |
| Dark mode | No contrast violations reported by axe on any route; no visual review beyond that. |
| Mobile overflow at 320px | Confirmed on /rules (F2) and on the static demo (F4). All other app routes: no overflow. |
| npm audit --omit=dev | `found 0 vulnerabilities`. |
| typecheck | Pass (tsc --noEmit, no output). |
| vitest | 7 files, 49 tests passed. |
| lint | No lint script exists (Confirmed absence). |
| Licences (package-lock) | MIT 151, Apache-2.0 22, MPL-2.0 14 (dev: lightningcss family), ISC, BSD, 0BSD, CC-BY-4.0 (caniuse-lite, build data), MIT-0. LGPL-3.0-or-later: 10 `@img/sharp-libvips-*` and 4 `@img/sharp-*` (Apache-2.0 AND LGPL combos), all optional, pulled in by `next` for image optimisation. The app uses no next/image (no `<Image>` found in grep); the binaries still ship in node_modules and potentially in the container image. No GPL/AGPL. |

## Confirmed findings

### F1 (P3) React hydration error #418 on /organisation
- File: frontend/src/pages/organisation.tsx:117, `formatDate(new Date().toISOString())` called during render.
- Root cause: the page is statically prerendered; the build-time date text differs from the client render, so React reports a text mismatch.
- Reproduce: production build, open http://localhost:3000/organisation in Chromium, listen for `pageerror`: "Minified React error #418 ... args[]=text". Occurred in all 4 runs (light/dark, 1366/320).
- Impact: console error, possible full client re-render, stale "now" date baked into HTML.
- Fix: compute the date in useEffect/client-only state, or drop the "now" text.

### F2 (P3) /rules overflows horizontally at 320px, with a keyboard trap-free but unlabelled scroller
- Reproduce: viewport 320x640, open /rules. documentElement scrollWidth 544 vs clientWidth 320 (probe), axe `scrollable-region-focusable` (1 node) in light mode. Offender: `table.data` (right edge ~695px). Screenshot: /tmp/agent_fe/rules320.png.
- Root cause (not verified in CSS): rules table is not constrained or wrapped in a focusable overflow container on narrow screens.
- Fix: wrap in a `tabindex=0` `role=region` `aria-label` scroll container with `overflow-x:auto`, or collapse columns on mobile.

### F3 (P4) No scheme/origin validation of server-supplied links
- Files: src/pages/notifications.tsx:25 (`n.link`), src/pages/index.tsx:43 (`s.link`), src/components/report/RuleResults.tsx:80 (`r.source_url`), src/pages/rules.tsx:127 (`s.url`).
- Reproduce (mocked API response for /api/v1/notifications): `link: "https://evil.example/phish"` is rendered as a normal link; clicking it navigated the tab to the external site. `javascript:` was neutralised by React 19 (see table), so the residual risk is off-site navigation and phishing if the API or ruleset data were attacker-influenced. `source_url` and `s.url` are opened in a new tab with rel noopener noreferrer.
- Fix: validate links with a helper (same-origin relative path starting with a single `/`, or https allowlist) in the schema (zod `refine`) before rendering. The demo's `safeUrl` is a model.

### F4 (P3) Static demo overflows at 320px
- Reproduce: serve /site (my server: /tmp/agent_fe/site.js), viewport 320x640, load `/`: scrollWidth 340 vs clientWidth 320. Culprit element not identified.
- Fix: find the element wider than the viewport (likely the findings table or hero) and constrain it or wrap in an overflow container.

### F5 (P4, design note) API key held in sessionStorage
- File: src/lib/auth.ts:4-21. Readable by any script that runs on the origin. Mitigated by the strict `script-src 'self'` CSP and no XSS sinks found; a CSP bypass or a compromised dependency would expose it. Prefer the cookie session (already supported) over pasted tokens for browsers; the login page and settings page encourage pasting a token. Low severity, informational.

### F6 (P4) Static demo has no CSP
- site/index.html has no CSP meta tag and the static host headers are not defined in the repo (not checked on the deployed host). app.js renders data with textContent and `safeUrl`, so no sink was found. Adding `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'">` (frame-ancestors needs a header) would be defence in depth.

## Limitations
- Local no-auth mode only. Accounts mode (cookie session, CSRF retry, role-gated pages) was not exercised. Case, report, document detail pages and review workflows were not driven with real data, so their axe, overflow and race behaviour is unverified.
- Mocked API data was used for the XSS and link probes; findings about real backend output (for example a ruleset with a hostile `source_url`) were not tested.
- Dark mode checked only through axe, not visually. Contrast at 320px was not re-run with axe in dark mode.
- Keyboard and focus order, focus visibility, form labels beyond axe (for example the `aria-label` only API-token input on /login) were not manually tested.
- Effort cap (about 45 tool calls plus a short extension) limited depth; the first browser run was invalid (wrong page origin causing CORS noise) and was re-run correctly.
- Servers were stopped at the end of the run.
