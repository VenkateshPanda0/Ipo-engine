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
* **`docker compose up` has not been run end to end by a person.** The images were written in a session
  with no container engine; since 2026-11-24 the `docker` workflow builds both images on every push,
  starts each and answers its health check, and scans each with Trivy (fixable HIGH and CRITICAL fail the
  build). What CI does not do is bring the two up together and click through the web app.

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

* ~~Dev-only npm advisories~~ (resolved 2026-11-25): vitest 5, vite 8 and `@vitejs/plugin-react` 6
  replaced vitest 2 / vite 5; the full `npm audit` (not only production) now reports 0 vulnerabilities
  and CI gates on it. The earlier "peer conflict" was npm refusing to upgrade in place while the old
  esbuild was still in the tree; regenerating the lockfile resolved it with no force flags.

* Starlette emits a deprecation warning from the `httpx`-based test client.
* The legacy v0 endpoints (`/screen/*`, `/reports/*`, `/reviews/*`, `/rules/*`) are
  kept for compatibility. They should be deprecated once clients move to `/api/v1`.
