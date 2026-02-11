# Governance Rollout Phase 0 Baseline

Date: 2026-02-11
Branch: `feat/governance-rollout-phase0-baseline`
Base: `develop/governance-engine`

## Scope

Phase 0 prep baseline for rollout:
- freeze a verified reference run
- document legacy -> canonical mapping for key compatibility fields
- capture deterministic artifact verification evidence

## Baseline Commands

Executed from repo root:

```bash
python3 -m pytest -q
python3 scripts/governance_lint.py
python3 scripts/build.py --out-dir dist --formats zip,tar.gz
```

## Baseline Results

- Tests: `283 passed, 1 skipped`
- Governance lint: `OK`
- Built artifacts:
  - `dist/governance-1.1.0-RC.2.zip`
  - `dist/governance-1.1.0-RC.2.tar.gz`
  - `dist/SHA256SUMS.txt`
  - `dist/verification-report.json`

Artifact hashes (`dist/SHA256SUMS.txt`):

- `6e0f1e7881d7a95c7b652baa863ae7a5f797db1864c98856d6b1c39580bfb583  governance-1.1.0-RC.2.zip`
- `0215eebd1ef91bc46c6debec90bfa0eb115de085d252dfcafa7404cbc8b9245a  governance-1.1.0-RC.2.tar.gz`

## Legacy -> Canonical Mapping (Phase 0)

### SESSION_STATE field aliases

- `SESSION_STATE.RepoModel` -> `SESSION_STATE.RepoMapDigest` (canonical wins when both exist)
- `SESSION_STATE.FastPath` + `SESSION_STATE.FastPathReason` -> `SESSION_STATE.FastPathEvaluation.*` (canonical source)

### Rulebook/profile filename compatibility

- Canonical profile filename: `profiles/rules_<profile>.md`
- Accepted legacy aliases:
  - `profiles/rules.<profile>.md`
  - `profiles/rules-<profile>.md`

### Reason-code compatibility boundary

- Audit reason keys are not canonical output reason codes.
- Canonical mapping source remains `diagnostics/AUDIT_REASON_CANONICAL_MAP.json` and bridge logic remains `diagnostics/map_audit_to_canonical.py`.

## Phase 1 Entry Checklist

Phase 1 (dual-read) can start when all are true:

- [x] baseline tests and lint are green
- [x] deterministic build artifacts were produced
- [x] verification sidecar exists (`dist/verification-report.json`)
- [x] compatibility mapping for profile IDs, reason-code bridge, and SESSION_STATE aliases is documented
