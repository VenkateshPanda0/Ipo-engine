# Repository settings to apply by hand

These are GitHub settings that no commit can change. Do them once, as the repository owner. Menu names
move around on GitHub; the **Settings** tab of the repository and the names below are what to look for.
Repository: `github.com/VenkateshPanda0/Ipo-engine` (renamed from `ipo-due-diligence-engine`).

## 0. Do these first

1. **Point your local clone at the new name** (the old address redirects but is not the real one):
   `git remote set-url origin https://github.com/VenkateshPanda0/Ipo-engine.git`
2. **History was rewritten on 2026-11-25.** One early commit carried an AI co-author trailer; it was
   removed from `main` with a one-time force-push (70 commits, same file contents, same authors and
   dates, new hashes from that commit on). Any other clone made before then must be refreshed
   (`git fetch origin && git reset --hard origin/main`, or re-clone), and a pull request or branch based on
   the old history will show as diverged. This is done, so turning on "block force pushes" below is safe.

## 1. Protect `main`

**Settings → Rules → Rulesets → New ruleset → New branch ruleset.**

- *Ruleset name*: `main`. *Enforcement status*: **Active**.
- *Target branches*: **Add target → Include default branch**.
- Tick:
  - **Restrict deletions**
  - **Block force pushes**
  - **Require linear history**
  - **Require a pull request before merging**: *Required approvals* `0` while you are the only
    maintainer (you cannot approve your own pull request), raise it when there is a second one.
    Tick *Dismiss stale pull request approvals when new commits are pushed*.
  - **Require status checks to pass**: tick *Require branches to be up to date before merging*, then
    **Add checks** and add these (they appear after each has run once):
    `python 3.12`, `python 3.13`, `frontend`, `end-to-end (Chromium)`, `api image`, `web image`,
    `analyze (python)`, `analyze (javascript-typescript)`, `gitleaks`.
- **Bypass list**: if you want to keep committing straight to `main` as the maintainer, add
  **Repository admin** under *Bypass list*. Be aware that a bypass applies to *every* rule in the
  ruleset, including force-push blocking. If you want force pushes blocked even for you, make two
  rulesets: one with the pull-request and status-check rules (and the bypass), and one with only
  *Restrict deletions* and *Block force pushes* and **no** bypass.
- **Create**.

Check it: a direct push of a failing commit, or a force-push, should be refused (the second only if
you chose the no-bypass ruleset).

## 2. Security features

**Settings → Code security** (called *Advanced Security* or *Code security and analysis* on some
accounts). Turn these on:

| Setting | Why |
|---|---|
| **Private vulnerability reporting** → Enable | `SECURITY.md` and the issue chooser send reporters here |
| **Dependency graph** → Enable | needed for the next two |
| **Dependabot alerts** → Enable | advisories for locked dependencies |
| **Dependabot security updates** → Enable | automatic fix pull requests for those alerts |
| **Secret scanning** → Enable | |
| **Push protection** (under Secret scanning) → Enable | blocks a push that contains a recognised secret |

`.github/dependabot.yml` already schedules weekly *version* updates (uv, npm, both Dockerfiles, GitHub
Actions); nothing else to switch on for that. Expect its pull requests to start appearing. They are
the one exception to "only `main`": each is a short-lived branch on GitHub that you merge or close.

**Code scanning:** the `codeql.yml` workflow runs CodeQL. In **Settings → Code security → Code
scanning**, do **not** also enable the *default setup* for CodeQL (the two conflict); leave it as
*Advanced (workflow)*. The Trivy and Scorecard results arrive in the same Code scanning page as
separate categories (`trivy-api`, `trivy-web`, `scorecard`).

## 3. Actions

**Settings → Actions → General.**

- *Actions permissions*: **Allow all actions and reusable workflows** is fine; every action in the
  workflows is pinned to a commit SHA. To be stricter, choose *Allow owner, and select non-owner
  actions* and list `actions/*`, `astral-sh/*`, `docker/*`, `github/codeql-action/*`,
  `aquasecurity/*`, `anchore/*`, `ossf/*`, `gitleaks/*`, `softprops/*`.
- *Workflow permissions*: **Read repository contents and packages permissions** (the workflows ask for
  more only where a job needs it). Leave *Allow GitHub Actions to create and approve pull requests*
  **off**.
- *Fork pull request workflows*: **Require approval for first-time contributors**.

## 4. GitHub Pages (the demo site)

**Settings → Pages → Build and deployment → Source: GitHub Actions.** (Already set; check it still
is. The `demo site` workflow deploys `site/` on changes to it.)

## 5. Container packages (after the first release)

The release workflow pushes `ghcr.io/venkateshpanda0/ipo-engine` and `.../ipo-engine-web`. A new
package is private. For each: your profile → **Packages** → the package → **Package settings**:

- **Change visibility → Public** (so `docker pull` works without logging in).
- **Connect repository → Ipo-engine** (so it shows on the repository page and inherits its access).

## 6. Repository page

**Settings → General** (and the gear next to *About* on the main page):

- Description: "IPO due diligence for Indian offer documents: page-cited, offline, no language model."
- Website: `https://venkateshpanda0.github.io/Ipo-engine/`
- Topics: `ipo`, `sebi`, `drhp`, `due-diligence`, `document-extraction`, `offline`.
- Features: **Issues** on (the issue forms need it); **Discussions** optional; **Wikis** and
  **Projects** off unless you use them.
- *Pull Requests*: **Allow squash merging** off if you want a linear history with the original
  commits, or on and *default to pull request title* if you prefer one commit per change; **Allow
  merge commits** off (linear history above forbids them); **Automatically delete head branches** on.

## 7. Clean up

- The stale remote branches `chore/versioning` and `ccr-71a22a3f-lrwqku` are gone (the second still
  held the old history). Dependabot creates short-lived `dependabot/...` branches for its pull
  requests; merge or close them from the **Pull requests** tab, and with **Automatically delete head
  branches** on (section 6) they disappear on merge.
- Delete any other branch you do not recognise: **Code → Branches**.

## 8. Only if you later publish to PyPI

Create the project on PyPI, add this repository and `release.yml` as a **trusted publisher** (no token
is needed), create an **Environment** named `pypi` (**Settings → Environments**) with *Required
reviewers* set to you, then uncomment the `pypi` job in `release.yml`.
