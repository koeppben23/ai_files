# Governance Rollout Phase 3 Legacy Removed

Date: 2026-02-11
Branch: `feat/governance-rollout-phase3-legacy-removed`
Base: `develop/governance-engine`

## Goal

Complete SESSION_STATE rollout by removing legacy-compat reads in phase 3 and
returning explicit deterministic recovery instructions for unsupported legacy
artifacts.

## Implemented Behavior

- `SessionStateRepository.load_with_result()` now distinguishes phase 2 and 3:
  - phase 2 (`rollout_phase == 2`): legacy aliases are allowed only when
    compatibility mode is explicitly enabled
  - phase 3+ (`rollout_phase >= 3`): legacy aliases are blocked, even if
    compatibility mode is enabled

- `SessionStateCompatibilityError` now carries deterministic recovery fields:
  - `primary_action`: one primary action for the operator
  - `next_command`: one command for deterministic recovery guidance

- Legacy-removed mode guidance contract:
  - reason code remains `BLOCKED-SESSION-STATE-LEGACY-UNSUPPORTED`
  - detail indicates legacy-removed mode and offending fields
  - recovery guidance points to deterministic migration command

- No-claim-without-evidence contract coverage:
  - added orchestrator contract test for quality claims (`tests green`,
    `static clean`, `no drift`)
  - claims remain `NOT_VERIFIED` unless required evidence IDs are present

## Acceptance Evidence

Executed checks:

```bash
${PYTHON_COMMAND} -m pytest -q tests/test_engine_orchestrator.py tests/test_engine_e2e_matrix.py tests/test_session_state_repository.py tests/test_reason_code_registry.py
${PYTHON_COMMAND} -m pytest -q
${PYTHON_COMMAND} scripts/governance_lint.py
```

Results:

- targeted tests: `48 passed`
- full suite: `297 passed, 1 skipped`
- governance lint: `OK`
