# Governance Template Blueprints

This document maps production-ready workflow templates to governance goals.

## Included templates

- `templates/github-actions/governance-pr-gate-shadow-live-verify.yml`
  - roles: shadow evaluator -> live verifier -> reviewer recompute
  - evidence: junit/lint exitcode/drift report (runner derives claims from evidence files in review mode)
  - reviewer recomputes from raw evidence only and verifies live-vs-review hash parity
  - optional tamper resistance: reviewer verifies evidence/result hashes before recompute
  - artifacts: shadow/live/review payloads + policy diff with activation/ruleset hash report

- `templates/github-actions/governance-ruleset-release.yml`
  - validates manifests and governance contracts
  - builds deterministic `manifest.json`, `lock.json`, `hashes.json` via `scripts/build_ruleset_lock.py`
  - verifies isolated rebuild hash parity before publishing artifacts
  - blocks release on non-deterministic lock state or hash mismatch

- `templates/github-actions/governance-golden-output-stability.yml`
  - executes canonical intents through real intent->engine->render script (`scripts/generate_golden_outputs.py`)
  - blocks output drift with both textual diff and SHA-256 manifest diff checks
  - blocks baseline edits in PRs (`BLOCKED-GOLDEN-BASELINE-MODIFIED-IN-PR`) to prevent regression masking

- `templates/github-actions/governance-golden-baseline-update.yml`
  - maintainer-only `workflow_dispatch` path for baseline replacement
  - requires explicit `UPDATE_GOLDENS` confirmation token
  - generates fresh baseline from real intent->engine->render pipeline and emits hash manifest
  - supports artifact-only review or optional commit/push to target branch

## Adoption guidance

- Treat templates as blueprints; adapt command hooks to your runner entrypoints.
- Keep reviewer recompute authoritative: never trust developer-produced gate status directly.
- Preserve artifact uploads on failure for deterministic diagnosis.
