# Governance Pipeline Roles Template

Template path:

- `templates/github-actions/governance-pipeline-roles.yml`

## Purpose

Provide deterministic CI role separation for governance decisions:

- `governance-developer`: produce evidence and benchmark artifacts
- `governance-reviewer`: authoritative gate recomputation from artifacts
- `governance-improver`: deterministic recovery card on non-pass outcomes

## Key hardening guarantees

- evidence-derived claims (not manual claim flags)
- reviewer recomputes gate (does not trust developer status field)
- artifact hash verification before reviewer decision
- always-upload artifacts for post-failure diagnosis
- minimal permissions and concurrency guard

## Exit code contract (`scripts/run_quality_benchmark.py`)

- `0` -> `PASS`
- `2` -> `NOT_VERIFIED`
- `3` -> `FAIL`
- `4` -> `BLOCKED`

Pipeline handling policy:

- reviewer treats only `0` as pass
- `2` fails check with explicit not-verified message
- `3` and `4` fail check as hard gate failures

## Drift report policy

- Pull requests: diff against base branch (`origin/<base_ref>...HEAD`)
- Manual dispatch fallback: diff `HEAD~1..HEAD` when available
