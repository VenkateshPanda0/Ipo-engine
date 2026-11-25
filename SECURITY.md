# Security policy

## Reporting a vulnerability

Please report it **privately**: on the repository's Security tab choose
**Report a vulnerability** (GitHub private vulnerability reporting). If that is not available to you,
write to **venkateshpanda00@gmail.com** with "IPO Engine security" in the subject. Do not open a public issue for a security
problem.

Include what you found, how to reproduce it (a sample file or request helps), the version
(`ipo --version`, or `package_version` from `/api/v1/system/health`), and what you think the impact
is. I will acknowledge a report within **5 days**, tell you whether I can reproduce it, and keep you
informed until it is fixed or I explain why it will not be. Please allow reasonable time to fix it
before disclosing; I will credit you in the changelog unless you prefer not to be named.

## Supported versions

Fixes go to the latest release only. The project is pre-1.0, with no long-term-support branches.

## Scope

In scope: the reader (`ipo`), the screening API and web app, and the container images built from
this repository, including their handling of untrusted PDFs, authentication, and the generated HTML.

Out of scope: a figure in a filing being wrong (use the "wrong figure" issue form: accuracy is
measured and published, and nothing here is investment or legal advice); findings that need an
operator to have set `ALLOW_UNAUTHENTICATED=true` or run development mode on an open network (both
are documented as unsafe there); denial of service by a very large legitimate filing within the
documented limits; third-party services this repository does not run.

## What to read first

The threat model, the authentication model, the headers and how to rotate keys are in
[`docs/security.md`](docs/security.md).
