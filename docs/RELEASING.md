# Releasing

A release is a tag. Pushing `vX.Y.Z` runs `.github/workflows/release.yml`, which checks the tag
against the package, runs the whole gate, builds the wheel and sdist, builds and pushes a
multi-architecture API image to GHCR, writes SBOMs, attests provenance, and creates the GitHub
Release from the CHANGELOG. Nothing is published to PyPI (the job is there, commented out).

Version numbers and when each one changes: `VERSIONING.md`.

## Dry run (no tag, nothing published)

Before the first real release, or after changing the workflow: **Actions → release → Run workflow**
(on `main`). It runs the gate, builds the wheel and sdist, makes both SBOMs and attests them, and builds
both images for amd64 and arm64, but it does **not** log in to the registry, push or attest an image, or
create a GitHub Release (a test, `tests/test_repo_files.py`, keeps it that way). The version checked is
the one in `pyproject.toml`, and its changelog section must exist. Download the `release-files`
artifact to look at what a release would contain.

## Checklist

1. **Start from a green `main`.** CI passing on the commit you will tag; `git status` clean.
2. **Decide the number** (SemVer; see `VERSIONING.md`). Edit `pyproject.toml` `version` and
   `frontend/package.json` + `frontend/package-lock.json` (the top two `version` fields) to match.
   `tests/test_versions.py` fails if they differ.
3. **Write the changelog.** In `CHANGELOG.md`, rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add a
   fresh empty `[Unreleased]` above it, and make sure every change since the last release is under
   Added, Changed, Fixed or Security, with its D-number where there is one. The workflow fails if the
   section for the version is missing or empty (`python3 tools/release_notes.py X.Y.Z` shows what
   would be published).
4. **Run the checks locally**: `tools/gate.sh; echo rc=$?`, then
   `cd frontend && npm run typecheck && npm test && npm run build`.
   If a bump of `ANALYSIS_VERSION`, the ruleset or `API_VERSION` is part of the release, confirm that
   `ipo eval` and `docs/status.md` carry the numbers for it.
5. **Commit and push** `chore(release): X.Y.Z` to `main` through a pull request; wait for CI.
6. **Tag and push the tag** (annotated, on the merged commit):
   `git tag -a vX.Y.Z -m "X.Y.Z" && git push origin vX.Y.Z`.
   For a trial run use a pre-release tag, `vX.Y.Z-rc.1`: it builds everything, marks the Release as a
   pre-release and does not move `latest`. The package version must still equal `X.Y.Z`.
7. **Verify the release artefacts** once the workflow is green:
   - The Release page has the wheel, the sdist, `sbom-python.cdx.json`, `sbom-frontend.cdx.json` and
     the notes from the changelog.
   - `gh attestation verify ipo_engine-X.Y.Z-py3-none-any.whl --repo VenkateshPanda0/Ipo-engine`
     succeeds (the same for the sdist).
   - Install the wheel in a clean environment: `uvx --from ./ipo_engine-X.Y.Z-py3-none-any.whl ipo --version`
     prints `ipo X.Y.Z`.
8. **Verify the image runs**: `docker run --rm -p 8000:8000 -e ALLOW_UNAUTHENTICATED=true
   ghcr.io/venkateshpanda0/ipo-engine:X.Y.Z` and `curl localhost:8000/api/v1/system/health` shows
   `package_version` X.Y.Z. (The image defaults to production, which refuses to start with no API
   keys; the flag is only for this check. Also check that without it the container exits with the
   `API_KEYS` message.) `docker buildx imagetools inspect` lists linux/amd64 and
   linux/arm64. Check the package's visibility in GitHub (`REPO_SETTINGS.md`).
9. **Check the demo site**: the Pages workflow runs on pushes to `main`; open the live page and
   confirm a brief loads. Rebuild `site/briefs.json` with `make demo` first if the analysis version
   changed.
10. **If something is wrong**: do not move or delete a published tag. Fix forward with a new patch
    release and say so in its changelog. A bad pre-release tag may be removed by the maintainer.

## What the workflow does not do

- It does not publish to PyPI.
- It does not sign the image with a key; it attests build provenance with GitHub's own identity
  (verify with `gh attestation verify oci://ghcr.io/venkateshpanda0/ipo-engine:X.Y.Z --repo ...`).
- The image SBOM is a workflow artifact (`sbom-image.cdx.json`), not attached to the Release.
- The web (Next.js) image is added with the container work (`build/docker`).
