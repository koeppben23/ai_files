# Pull Request Checklist

## Conventional PR Title (Required)

Your PR title must follow Conventional Commits.

Accepted pattern:

`^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]+\))?!?: .+`

Examples:

- `feat(governance): harden profile/addon principal gates and score calibration`
- `fix(installer): handle unicode paths`
- `docs(changelog): document principal hardening updates`

Before requesting review, verify the PR title starts with a valid type in lowercase and contains `: `.

---

## MD Files Change (If applicable)

**Complete this section if your PR modifies:** `master.md`, `rules.md`, `start.md`, or thematic rails in `docs/governance/rails/`

### Changed Files

<!-- List the MD files modified -->

### Affected Contracts

<!-- Which contracts from MD_RAILS_COVERAGE_MATRIX.md are affected? -->

### Affected Heuristics

<!-- Which cognitive heuristics might be impacted? -->

### Matrix Updated

- [ ] Yes - `docs/governance/MD_RAILS_COVERAGE_MATRIX.md` Change Log updated
- [ ] No - Not an MD change

### Regression Risk

- [ ] Low
- [ ] Medium
- [ ] High

### Verification Completed

- [ ] `governance_lint.py` passes
- [ ] MD rails coverage checks pass
- [ ] Semantic review: Intended behavior and guidance preserved
