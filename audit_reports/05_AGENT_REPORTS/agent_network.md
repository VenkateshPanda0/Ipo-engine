# Agent report: network / SSRF / webhooks / S3 / SMTP / shares / exports / backup

Branch audit/remediation-2026-11. No tracked file modified, nothing committed. Scripts are in /tmp/agent_net/ (ssrf.py, api_ssrf.py, sender.py, rest.py), localhost fakes only.
Python 3.12.3. Effort-capped, so some checks are by code reading only (marked).

## Scope and method
Read: network/{http,webhook_http,oidc,s3,smtp}.py, services/{webhooks,mailer,shares,tabular,backup}.py, api/routers/share.py, webhook/share/export routes in routers/accounts.py and v1.py, config. services/lifecycle.py was only grepped (export_org writes a zip; there is no zip/tar reader anywhere in src). Reproduced via validate_target on ~40 URLs, API-level calls (TestClient with the repo's accounts_world fixtures), PinnedSender against local fake servers, and direct calls into tabular, backup, S3Store and UrllibHttp.

## Confirmed findings

### F1 (P3) SSRF filter accepts NAT64 and IPv4-compatible IPv6 literals
webhook_http.py:134-137 relies only on `ipaddress.ip_address(ip).is_global`. Python 3.12 reports these as global:
`https://[64:ff9b::7f00:1]/`, `https://[64:ff9b::a9fe:a9fe]/` (NAT64 form of 169.254.169.254), `https://[::127.0.0.1]/`, plus `[ff02::1]` and deprecated site-local `[fec0::1]`.
Repro: `python /tmp/agent_net/ssrf.py` (ALLOWED lines); `python /tmp/agent_net/api_ssrf.py` shows POST /api/v1/webhooks answering 201 for `https://[64:ff9b::a9fe:a9fe]/latest` and `https://[::127.0.0.1]/x`.
Impact: a customer admin can point a webhook at cloud metadata or internal IPv4 hosts when the deployment has a NAT64/DNS64 gateway (IPv6-only clusters). `::127.0.0.1` could not be exercised: this sandbox has no IPv6 (connect gave EAFNOSUPPORT), so its reachability is unverified. Without NAT64 the practical impact is nil.
Fix: after is_global, unwrap `ipv4_mapped`, `sixtofour`, `teredo`, and reject 64:ff9b::/96, 64:ff9b:1::/48, ::/96, ff00::/8, fec0::/10; or resolve to AF_INET only. Re-check the unwrapped v4 address with is_global.

### F2 (P3) Slow-response DoS of the single webhook dispatcher thread
webhook_http.py:177-182 sets a 10 s per-socket-operation timeout, not a total deadline. `resp.read(4096)` blocks until 4096 bytes or EOF, and a server dripping 1 byte every <10 s keeps it alive. WebhookDispatcher (webhooks.py:461-481) is one thread that sends deliveries sequentially.
Repro: sender.py /drip endpoint (1 byte per 0.5 s): `PinnedSender.send` blocked 50.03 s until the fake gave up; with a longer drip the bound is about 4096 x 10 s per address. One malicious endpoint therefore stalls every organisation's deliveries. The 60 s lease (LEASE_S) can also expire mid-send, so another dispatcher could pick the same delivery up (by reading only).
Fix: total wall-clock deadline (e.g. a socket timeout that shrinks against a monotonic deadline), read only the status line and skip the body, or dispatch with a worker pool plus per-host limits.

### F3 (P3) Unhandled ValueError gives HTTP 500 on bad webhook URL ports
webhook_http.py:126 `parts.port` raises ValueError (not HttpError) for `https://8.8.8.8:99999/x` or `:abc`; services/webhooks.py:113-116 catches only HttpError.
Repro: api_ssrf.py: POST /api/v1/webhooks with those URLs returned 500 INTERNAL_ERROR, and PATCH /webhooks/{id} returned 500 with a logged traceback. Admin-only, no bypass found; it is an error-handling and log-noise bug. Port 0 is accepted and silently becomes 443 (`parts.port or 443`).
Fix: wrap urlsplit/port access in try/except ValueError and raise HttpError; test `parts.port is None` rather than falsiness.

### F4 (P3) Restore does not bind backup contents to the manifest
backup.py:118-123 and 169-170:
(a) verify() joins manifest keys onto the folder with no containment check, so a tampered manifest may name `../../secret.txt` and verify() passes if the hash matches (reproduced; it is only a hash oracle).
(b) restore() copies every `documents/*.pdf` present in the folder whether or not the manifest lists it, with no check that the filename is a sha256 or matches the content. Reproduced: an unlisted `evil-name.pdf` verified OK and was restored.
(c) shutil.copy2 follows symlinks. Reproduced: `documents/link.pdf` -> /path/secret.txt was restored as a regular file containing the target's content.
(d) A manifest without "files" raises KeyError (not BackupError).
The manifest is unsigned, so anyone who can write the backup directory can rewrite it. Exploitation needs write access to the backup folder, hence P3. The restored document store is content-addressed; whether FileStore re-hashes on read was not checked (unverified).
Fix: only restore names listed in the manifest, require `^[0-9a-f]{64}\.pdf$`, reject symlinks (`is_symlink`) and paths that resolve outside the folder, validate manifest schema, and optionally HMAC-sign the manifest.

### F5 (P4) UrllibHttp follows redirects despite its docstring
network/http.py:40-49: require_https() runs only on the initial URL; urlopen follows 3xx. Repro (rest.py): GET to 127.0.0.1 with a 302 to http://127.0.0.2 succeeded and returned that server's JSON, although require_https refuses 127.0.0.2 directly. Only reachable via operator-configured OIDC issuer, discovery document, token_endpoint or jwks_uri, so it needs a malicious or compromised IdP; I tested loopback only and did not test an https-to-http downgrade. Fix: install an opener with a redirect handler that re-runs require_https, or refuse redirects.

### F6 (P4) Small hardening and correctness issues
- s3.py:23 `_HEX64` uses `$`, which matches before a trailing newline: digest `"a"*64+"\n"` is accepted (reproduced). The key stays under `documents/` (the newline is percent-encoded), so no traversal; use `fullmatch`.
- tabular.py:387-396 prefixes numeric negatives: `cell_text(-5)` returns `'-5` (reproduced). This corrupts legitimate numbers in the CSV/XLSX; apply the guard to str values only. In XLSX the cells are inlineStr, so formulas never execute and the apostrophe is cosmetic. CSV header cells are not sanitised, but all headers are static literals (v1.py:700-720), so not exploitable today.
- services/webhooks.py:84 `hmac.compare_digest` on str raises TypeError for a non-ASCII header (reproduced). verify_signature is a receiver and test helper only; compare bytes.
- webhooks.py:208-229: deliveries output omits payload and secrets; last_error holds exception text capped at 300 chars (read only).

## Checks with no finding
| Check | Result |
|---|---|
| Decimal/octal/hex/short IPv4 (2130706433, 0x7f000001, 0177.0.0.1, 127.1), 0.0.0.0, `0` | Not Found (blocked, ssrf.py) |
| IPv6 ::1, ::ffff:127.0.0.1, ::ffff:7f00:1, ::ffff:169.254.169.254, fe80::, fc00::, 2002:7f00:1::, 2001::/32 Teredo, ::, 2001:db8:: | Not Found (blocked) |
| 169.254.169.254, CGNAT 100.64/10, 198.18/15, 240/4, 255.255.255.255 | Not Found (blocked) |
| userinfo (`a@127.0.0.1`, `\@` tricks) | Not Found (rejected as credentials) |
| Trailing-dot `localhost.` (does not resolve here), unicode and fullwidth digit hosts (resolve to 127.0.0.1, blocked) | Not Found |
| Non-https schemes, http without ALLOW_PRIVATE_WEBHOOK_TARGETS | Not Found |
| DNS rebinding between check and connect | Not Found: one resolution, connection pinned to the checked IP (`_Pinned`), TLS SNI/verify against original host; a mixed public+private answer is rejected wholesale (existing test) |
| Redirects | Not Found: PinnedSender does not follow (302 returned as status, sender.py) |
| CRLF header injection via URL path | Not Found: urlsplit strips CR/LF (`/a\r\nX-Evil: 1` becomes `/aX-Evil: 1`); event name is a fixed enum; headers are fixed values |
| Unbounded response read | Not Found for size (read(4096)); 300 response headers raised HTTPException and was handled; time bound is F2 |
| HMAC construction | Not Found: HMAC-SHA256 over "t.body", per-endpoint secret derived from server key, id and version; fresh timestamp per attempt; compare_digest used (replay window is enforced by receivers, tolerance 300 s in verify_signature) |
| Secret leakage in list/deliveries/audit | Not Found: secret only on create and rotate; audit details hold only events; list output verified |
| Cross-org webhook access (read deliveries, rotate) | Not Found: 404 for org B (api_ssrf.py); all webhook routes admin-only |
| S3 key traversal/injection, SigV4 | Not Found beyond F6: digest validated before key building; `../` digests refused; canonical path quoted once and consistently with the URL; signed headers include host, x-amz-date, content sha. Not tested against real AWS or MinIO (unverified). Prefix and endpoint are operator config and are not sanitised (`b/../p/documents/...` was produced from prefix `../p`). |
| SMTP header injection | Not Found by reading: EmailMessage raises ValueError on a line break in From/To/Subject and the code maps it to MailError; the organisation and inviter names are collapsed by `_one_line`. Not exercised against a fake SMTP server (unverified). STARTTLS/SSL use create_default_context. |
| Formula injection in exports | Not Found for = + - @ TAB CR (reproduced); leading `\n`, leading space and fullwidth `＝` are not prefixed (not exploitable in Excel by itself). Sheet name is a static literal; `escape()` does not escape `"`, which matters only if the name ever becomes user-controlled. |
| XLSX/ZIP bomb, zip-slip | Not applicable: the code only writes zips (tabular, lifecycle export_org); there is no zip/tar reader in src (grep) |
| Share token entropy and enumeration | Not Found: `token_urlsafe(32)` (256 bits), stored as unsalted SHA-256, lookup by hash equality, one 404 answer for unknown/expired/revoked, length gate 20-100, per-IP limiter, no-store and CSP headers, org-scoped create/list/revoke (read only; not exercised over HTTP) |
| OIDC token validation | Not Found by reading: RS256 only, kid lookup, rate-limited JWKS refetch, iss/aud/azp/exp/iat/nonce checks with compare_digest, email_verified required downstream |

## Limitations
Not exercised: real TLS, DNS rebinding with a real resolver, IPv6 connectivity, a real SMTP or S3 server, share-link HTTP behaviour, rate-limiter behaviour behind a reverse proxy (whether `request.client.host` is the proxy address was not checked), lifecycle.py internals, and whether the share page or report HTML escapes content. The effort cap (~40 tool calls) applied.
