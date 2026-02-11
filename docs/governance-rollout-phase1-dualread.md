# Governance Rollout Phase 1 Dual-Read

Date: 2026-02-11
Branch: `feat/governance-rollout-phase1-dualread`
Base: `develop/governance-engine`

## Goal

Enable dual-read compatibility for legacy SESSION_STATE aliases while ensuring
write paths persist only canonical fields.

## Implemented Behavior

- `SessionStateRepository.load()` now performs dual-read normalization:
  - `SESSION_STATE.RepoModel` -> `SESSION_STATE.RepoMapDigest` (when canonical is absent)
  - `SESSION_STATE.FastPath` + `SESSION_STATE.FastPathReason` -> `SESSION_STATE.FastPathEvaluation` (when canonical is absent)

- `SessionStateRepository.save()` now canonicalizes before write:
  - drops legacy aliases: `RepoModel`, `FastPath`, `FastPathReason`
  - writes canonical fields only (`RepoMapDigest`, `FastPathEvaluation`)

- Rollout guardrails:
  - explicit `rollout_phase` support (Phase 1 dual-read is opt-in behavior)
  - canonical hash helper `session_state_hash(...)` normalizes legacy aliases before hashing
  - migration audit trail via `SESSION_STATE.migration_events[]` with from/to fields, timestamp, and engine version
  - legacy read -> canonical write -> reread idempotence covered by dedicated test

## Acceptance Evidence

Executed checks:

```bash
python3 -m pytest -q tests/test_session_state_repository.py
python3 -m pytest -q
python3 scripts/governance_lint.py
```

Results:

- `tests/test_session_state_repository.py`: `15 passed`
- full suite: `290 passed, 1 skipped`
- governance lint: `OK`

## Notes

This phase is intentionally behavior-preserving for canonical consumers and
compatibility-friendly for legacy artifacts. It does not enable engine-only
rejection yet (Phase 2).
