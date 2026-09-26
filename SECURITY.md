# Security

## Running code you don't control

CodeSentinel executes code: it runs test suites, and with **Paste Your Own Repo** it clones a GitHub repository and runs its install scripts and tests.

- The built-in demo repository only runs code from this project.
- **Paste Your Own Repo is off by default** (`ALLOW_USER_REPOS=false`). Enabling it runs that repository's code on the machine hosting CodeSentinel. Only enable it on a machine you control, for repositories you trust.
- Current isolation is process-level: a per-run copy and virtualenv, timeouts, size limits, and secrets stripped from every subprocess environment. It is **not** a security boundary against malicious code — a container sandbox is planned. Keep `ALLOW_USER_REPOS=false` on any public deployment.
- API keys belong in `backend/.env`, which is git-ignored. Never commit keys.

## Reporting a vulnerability

Please don't open a public issue for security problems. Use GitHub's **Report a vulnerability** (Security tab → Advisories) on this repository, or contact the maintainer through their GitHub profile. You'll get a response as soon as possible.
