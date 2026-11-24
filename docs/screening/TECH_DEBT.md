# Technical debt register

## High

* **Answer keys are not human-verified.** The benchmark answer keys were prepared by an
  AI assistant from poppler text. A person must check them against the PDFs before
  the benchmark can be cited as validation.
* **No legal review.** See REGULATORY_VALIDATION.md. The SCRR and exchange rules rest
  on secondary or unverified sources.
* **The benchmark is small.** It has 8 DRHPs (5 development, 3 holdout) and covers
  only the Reg 6 eligibility figures. The holdout is too small to give tight error
  bounds.
* **Narrative facts are pattern-based.** Reg 5 declarations, governance, RPT and
  litigation inputs are entered manually. Narrative extraction only suggests the
  listing route and document type.

* **The web image fixes the API address at build time.** `NEXT_PUBLIC_API_BASE_URL` is inlined by
  Next.js when the app is built, so the published image only works against `http://localhost:8000`
  (the compose default); any other address needs a rebuild (`--build-arg`). A runtime setting
  (a small `/config.json` the app reads at start) would remove this.
* **The container images were written without a container engine.** The build session had a Docker
  client but no daemon, so `docker compose up` was not run there. What was run: the locked,
  non-editable install that the API builder stage performs, started with `uvicorn` and checked at
  `/api/v1/system/health`; the Next.js standalone build served from the layout the web image
  copies; `docker compose config`. The `docker` workflow builds, starts and scans both images in CI.

## Medium

* **SQLite only.** This suits a single-node local or demo deployment. Multi-user
  production use needs PostgreSQL, which needs a migration run and append-only
  enforcement other than SQLite triggers.
* **In-process worker threads.** A restart marks in-flight extractions as failed (they
  can be retried). There is no distributed queue.
* **Rate limiting is in-memory** and per process.
* **OCR is English only** (Tesseract `eng`). OCR values are never high-confidence.
* **API keys are configured through environment variables.** There is no SSO/OIDC
  and no key rotation UI.
* **Basis consistency.** The rules do not check that the three Reg 6(1) years share a
  statement basis (see REGULATIONS.md, question 4).

## Low

* **Dev-only npm advisories.** `vitest` 2.x and `vite` 5 carry advisories (2026-10-04
  audit). They only affect the local test runner, and the Vitest UI server is not
  used. Production dependencies audit clean. The fix is a major upgrade (vitest 5),
  which currently hits a peer-dependency conflict with `@vitejs/plugin-react`.

* Starlette emits a deprecation warning from the `httpx`-based test client.
* The legacy v0 endpoints (`/screen/*`, `/reports/*`, `/reviews/*`, `/rules/*`) are
  kept for compatibility. They should be deprecated once clients move to `/api/v1`.
