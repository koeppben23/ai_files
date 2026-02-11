# Governance Template Blueprints

This document maps production-ready workflow templates to governance goals.

## Included templates

- `templates/github-actions/governance-pr-gate-shadow-live-verify.yml`
  - roles: shadow evaluator -> live verifier -> reviewer recompute
  - evidence: junit/lint exitcode/drift report
  - artifacts: shadow/live/review payloads + policy diff

- `templates/github-actions/governance-ruleset-release.yml`
  - validates manifests and governance contracts
  - builds deterministic `manifest.json`, `lock.json`, `hashes.json`
  - blocks release on non-deterministic lock state

- `templates/github-actions/governance-golden-output-stability.yml`
  - executes canonical intents and compares against baseline goldens
  - blocks output drift unless `ALLOW_GOLDEN_UPDATE=1`

## Adoption guidance

- Treat templates as blueprints; adapt command hooks to your runner entrypoints.
- Keep reviewer recompute authoritative: never trust developer-produced gate status directly.
- Preserve artifact uploads on failure for deterministic diagnosis.
