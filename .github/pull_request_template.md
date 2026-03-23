# Pull Request Checklist

## Legacy Teardown Contract (Required)

- [ ] Welche alte Autoritaet wird in diesem PR entfernt?
- [ ] Welche neue Autoritaet ist jetzt SSOT?
- [ ] Welche CI-Gates decken den Scope ab (`legacy-scan`, `ssot-scan`, `install-smoke`, `bootstrap-smoke`, `delete-barrier`)?
- [ ] Welcher echte Install-/Bootstrap-Test lief lokal?
- [ ] Welche Duplikate wurden geloescht?

PRs ohne diese Angaben sind nicht mergefaehig.

## Conventional PR Title (Required)

Your PR title must follow Conventional Commits.

Accepted pattern:

`^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: .+`

Examples:

- `feat(governance): harden profile/addon principal gates and score calibration`
- `fix(installer): handle unicode paths`
- `docs(changelog): document principal hardening updates`

Before requesting review, verify the PR title starts with a valid type in lowercase and contains `: `.
