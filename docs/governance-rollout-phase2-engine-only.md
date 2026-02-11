# Governance Rollout Phase 2 Engine-Only

Date: 2026-02-11
Branch: `feat/governance-rollout-phase2-engine-only`
Base: `develop/governance-engine`

## Goal

Move SESSION_STATE handling to engine-only defaults in phase 2: legacy aliases are
fail-closed by default, with an explicit compatibility mode for controlled
transitional reads.

## Implemented Behavior

- `SessionStateRepository.load()` now enforces phase-specific behavior:
  - phase 1 (`rollout_phase == 1`): dual-read normalization remains unchanged
  - phase 2+ (`rollout_phase >= 2`): legacy aliases are blocked by default with
    `BLOCKED-SESSION-STATE-LEGACY-UNSUPPORTED`

- Explicit compatibility mode can be enabled in phase 2+:
  - config flag: `SessionStateRepository(..., legacy_compat_mode=True)`
  - env flag: `GOVERNANCE_SESSION_STATE_LEGACY_COMPAT_MODE=true`
  - behavior: allows legacy read normalization and emits
    `WARN-SESSION-STATE-LEGACY-COMPAT-MODE` through structured load metadata via
    `SessionStateRepository.load_with_result()`
  - backward compatibility: `SessionStateRepository.load()` still mirrors the same
    warning into `SessionStateRepository.last_warning_reason_code`

- Fail-closed guardrails:
  - invalid environment values for the compatibility switch raise `ValueError`
    (including empty string values)
  - unsupported legacy aliases in engine-only mode raise
    `SessionStateCompatibilityError` with canonical reason code and detail

## Acceptance Evidence

Executed checks:

```bash
python3 -m pytest -q tests/test_session_state_repository.py tests/test_reason_code_registry.py
python3 -m pytest -q
python3 scripts/governance_lint.py
```

Results:

- targeted tests: `23 passed`
- full suite: `295 passed, 1 skipped`
- governance lint: `OK`

## Notes

This phase changes load-time compatibility semantics only. Canonical write
behavior remains unchanged: save paths still normalize aliases and persist
canonical SESSION_STATE fields.
