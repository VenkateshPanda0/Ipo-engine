# API reference

Generated from the running application by `tools/api_doc.py`; a test fails if this
file is out of date. The interactive version is at `/docs` when `APP_ENV` is not
`production`.

**Authentication.** Send `Authorization: Bearer <token>` (a personal token from
`POST /api/v1/tokens`, or a key from `API_KEYS`), or use the browser session cookie
with the `X-CSRF-Token` header on every change. Roles, lowest to highest: viewer,
analyst, reviewer, admin. An id that belongs to another organisation answers 404, the
same as an id that does not exist. Errors are
`{"error": {"code", "message", "request_id"}}`.

**Version.** API 2.0.0. Breaking changes bump the major version;
the unversioned routes are deprecated (see `docs/VERSIONING.md`).

## Cases, documents, reviews, screenings, reports

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/cases` | List Cases |
| POST | `/api/v1/cases` | Create Case |
| DELETE | `/api/v1/cases/{case_id}` | Permanently delete a case, its documents and its history. ``confirm`` is its exact name. |
| GET | `/api/v1/cases/{case_id}` | Get Case |
| PATCH | `/api/v1/cases/{case_id}` | Update Case |
| PUT | `/api/v1/cases/{case_id}/assignee` | Assign Case |
| GET | `/api/v1/cases/{case_id}/comments` | List Comments |
| POST | `/api/v1/cases/{case_id}/comments` | Add Comment |
| DELETE | `/api/v1/cases/{case_id}/comments/{comment_id}` | Delete Comment |
| GET | `/api/v1/cases/{case_id}/data` | Case Data |
| PUT | `/api/v1/cases/{case_id}/data` | Replace Case Data |
| GET | `/api/v1/cases/{case_id}/data/versions` | Case Versions |
| GET | `/api/v1/cases/{case_id}/documents` | Case Documents |
| POST | `/api/v1/cases/{case_id}/documents` | Upload a PDF. Validation is synchronous; extraction runs in the background. |
| PATCH | `/api/v1/cases/{case_id}/fields` | Set Fields |
| GET | `/api/v1/cases/{case_id}/history` | Case History |
| GET | `/api/v1/cases/{case_id}/screenings` | Case Screenings |
| POST | `/api/v1/cases/{case_id}/screenings` | Screen Case |
| GET | `/api/v1/dashboard` | Dashboard View |
| GET | `/api/v1/documents` | List Documents |
| GET | `/api/v1/documents/{document_id}` | Get Document |
| DELETE | `/api/v1/documents/{document_id}/content` | Delete Document Content |
| GET | `/api/v1/documents/{document_id}/content` | Document Content |
| GET | `/api/v1/documents/{document_id}/extraction` | Document Extraction |
| GET | `/api/v1/documents/{document_id}/pages/{page}/image` | Render one page as PNG for the evidence viewer. |
| GET | `/api/v1/documents/{document_id}/reader` | The reader's brief for this document: status, and the brief once it is ready. |
| POST | `/api/v1/documents/{document_id}/reader` | Start the reader on the stored file. Safe to call again: it never runs twice. |
| POST | `/api/v1/documents/{document_id}/retry` | Retry Document |
| GET | `/api/v1/exports/{what}` | The case list or the report list as a spreadsheet (what you can see, nothing more). |
| GET | `/api/v1/me` | Me |
| GET | `/api/v1/reports` | List Reports |
| GET | `/api/v1/reports/{report_id}` | Get Report |
| GET | `/api/v1/reports/{report_id}/export` | Export Report |
| GET | `/api/v1/reports/{report_id}/shares` | List Shares |
| POST | `/api/v1/reports/{report_id}/shares` | A read-only link to this report. The link is in this response only. |
| DELETE | `/api/v1/reports/{report_id}/shares/{share_id}` | Revoke Share |
| GET | `/api/v1/reports/{report_id}/sign-off` | Get Sign Off |
| POST | `/api/v1/reports/{report_id}/sign-off` | Sign Off |
| GET | `/api/v1/review-items` | Review Items |
| POST | `/api/v1/review-items/{item_id}/resolve` | Resolve Item |
| GET | `/api/v1/rules` | Rules |
| GET | `/api/v1/rules/{rule_id}` | Rule |
| GET | `/api/v1/rulesets` | Rulesets |
| GET | `/api/v1/system/capabilities` | Capabilities |
| GET | `/api/v1/system/health` | Liveness plus basic dependency status (no authentication). |
| GET | `/api/v1/system/ready` | Readiness: database reachable and rules loaded. |

## Organisation, members, tokens, settings, webhooks

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/me/export` | What the service holds about the signed-in person. |
| GET | `/api/v1/notifications` | Notifications |
| POST | `/api/v1/notifications/read` | Read All Notifications |
| POST | `/api/v1/notifications/{notification_id}/read` | Read Notification |
| GET | `/api/v1/onboarding` | Onboarding |
| DELETE | `/api/v1/org` | Switch the organisation off. Pass its exact name as ``confirm``. |
| GET | `/api/v1/org` | Get Org |
| PATCH | `/api/v1/org` | Rename Org |
| GET | `/api/v1/org/export` | Everything the organisation holds, as a zip of JSON files (and the PDFs if asked). |
| GET | `/api/v1/org/members` | List Members |
| POST | `/api/v1/org/members` | Add an existing or new person by email (sign-in links come with invitations). |
| DELETE | `/api/v1/org/members/{user_id}` | Remove Member |
| PATCH | `/api/v1/org/members/{user_id}` | Change Role |
| GET | `/api/v1/org/settings` | Get Settings |
| PATCH | `/api/v1/org/settings` | Patch Settings |
| GET | `/api/v1/org/usage` | Org Usage |
| GET | `/api/v1/saved-filters` | List Saved |
| POST | `/api/v1/saved-filters` | Save Filter |
| DELETE | `/api/v1/saved-filters/{filter_id}` | Delete Saved |
| GET | `/api/v1/tokens` | List Tokens |
| POST | `/api/v1/tokens` | The token is in this response only; it cannot be shown again. |
| DELETE | `/api/v1/tokens/{token_id}` | Revoke Token |
| GET | `/api/v1/webhooks` | List Webhooks |
| POST | `/api/v1/webhooks` | The signing secret is in this response (and again on rotation), nowhere else. |
| DELETE | `/api/v1/webhooks/{webhook_id}` | Delete Webhook |
| PATCH | `/api/v1/webhooks/{webhook_id}` | Patch Webhook |
| GET | `/api/v1/webhooks/{webhook_id}/deliveries` | Webhook Deliveries |
| POST | `/api/v1/webhooks/{webhook_id}/deliveries/{delivery_id}/redeliver` | Redeliver |
| POST | `/api/v1/webhooks/{webhook_id}/rotate` | Rotate Webhook |
| POST | `/api/v1/webhooks/{webhook_id}/test` | Test Webhook |

## Sign-in, sessions, invitations

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/auth/callback/google` | Callback Google |
| GET | `/api/v1/auth/csrf` | Csrf |
| GET | `/api/v1/auth/invitation` | What an invitation link is for, so the page can say 'Join X as reviewer' before sign-in. |
| GET | `/api/v1/auth/login/google` | Login Google |
| POST | `/api/v1/auth/logout` | Logout |
| GET | `/api/v1/auth/organisations` | My Organisations |
| GET | `/api/v1/auth/providers` | Providers |
| GET | `/api/v1/auth/sessions` | List Sessions |
| POST | `/api/v1/auth/sessions/revoke-others` | Revoke Other Sessions |
| DELETE | `/api/v1/auth/sessions/{session_ref}` | Revoke Session |
| POST | `/api/v1/auth/switch-org` | Switch Org |
| GET | `/api/v1/org/invitations` | List Invitations |
| POST | `/api/v1/org/invitations` | The link is in this response only. Send it to the person (e-mail delivery is optional). |
| DELETE | `/api/v1/org/invitations/{invitation_id}` | Revoke Invitation |

## Public share links

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/shared/{token}` | Open Share |
