# Governance Epic Abnahme Matrix

This matrix maps each requested epic to concrete implementation paths and executable tests.

## Epic 1 - Reader auf echte Nutzerfuehrung umbauen

- Status: Implemented
- Code paths:
  - `governance/entrypoints/session_reader.py` (`format_guided_snapshot`, guided sections, single footer)
- Evidence tests:
  - `tests/test_session_reader_guided_contract.py`
  - `tests/test_session_reader.py`
  - `tests/test_bootstrap_persistence_e2e.py`

## Epic 2 - Evidence Presentation als echte Presentation

- Status: Implemented
- Code paths:
  - `governance/entrypoints/session_reader.py` (`Presented review content`, full plan body rendering)
  - `governance/entrypoints/review_decision_persist.py` (package completeness checks)
- Evidence tests:
  - `tests/test_session_reader_guided_contract.py`
  - `tests/test_review_decision_persist_entrypoint.py`
  - `tests/test_p6_gate_consistency.py`

## Epic 3 - Governance-Entscheidung und Implementierungs-Entscheidung trennen

- Status: Implemented
- Code paths:
  - `governance/entrypoints/review_decision_persist.py` (plan/governance decision contract)
  - `governance/entrypoints/implementation_decision_persist.py` (implementation-result decision contract)
  - `governance/entrypoints/session_reader.py` (separate presentation gates)
- Evidence tests:
  - `tests/test_review_decision_persist_entrypoint.py`
  - `tests/test_implementation_decision_persist_entrypoint.py`
  - `tests/test_p6_gate_consistency.py`

## Epic 4 - /implement mit echter operativer Wirkung

- Status: Implemented
- Code paths:
  - `governance/entrypoints/implement_start.py` (artifact generation, changed files, fail-closed blocked status)
- Evidence tests:
  - `tests/test_implement_start_entrypoint.py`

## Epic 5 - Interne Implementierungs-Review-/Revisions-/Verifikationsschleife

- Status: Implemented
- Code paths:
  - `governance/entrypoints/implement_start.py` (execution/self-review/revision/verification states and loop)
  - `governance/entrypoints/session_reader.py` (execution progress rendering)
- Evidence tests:
  - `tests/test_implement_start_entrypoint.py`
  - `tests/test_session_reader.py`

## Epic 6 - Implementation Presentation als echte Ergebnispraesentation

- Status: Implemented
- Code paths:
  - `governance/entrypoints/session_reader.py` (Implementation Presentation layout)
  - `governance/entrypoints/implementation_decision_persist.py` (presentation completeness + receipt checks)
- Evidence tests:
  - `tests/test_session_reader_guided_contract.py`
  - `tests/test_implementation_decision_persist_entrypoint.py`

## Epic 7 - Recovery und Blocker bereinigen

- Status: Implemented
- Code paths:
  - `governance/engine/next_action_resolver.py` (single canonical next-action resolution)
  - `governance/entrypoints/session_reader.py` (normal path vs blocker section rendering)
- Evidence tests:
  - `tests/test_session_reader_guided_contract.py` (no Recovery action in happy path, single footer)
  - `tests/test_session_reader.py`

## Epic 8 - Token/Phase-Felder enttechnisieren

- Status: Implemented
- Code paths:
  - `governance/entrypoints/session_reader.py` (`_display_phase` user-facing phase labels)
- Evidence tests:
  - `tests/test_session_reader_guided_contract.py::test_guided_edge_phase_display_hides_internal_token_labels`

## Epic 9 - /review auf PRs operativ eindeutig machen

- Status: Partial
- Implemented in this branch:
  - Governance presentation/decision path and contracts for review decisions are hardened.
- Remaining for full closure:
  - Dedicated `/review` PR execution logic with remote-first fetch/base resolution, isolated local fallback, and fail-closed stale-ref/SHA guards in the review execution path itself.

## Epic 10 - Harte Test- und Abnahmevertraege

- Status: Implemented for governance output/decision/implement flow contracts
- Code paths and tests:
  - Reader contract: `tests/test_session_reader_guided_contract.py`, `tests/test_session_reader.py`
  - Governance review decision blocking: `tests/test_review_decision_persist_entrypoint.py`, `tests/test_p6_gate_consistency.py`
  - Implement fail-closed/evidence: `tests/test_implement_start_entrypoint.py`
  - Implementation decision constraints: `tests/test_implementation_decision_persist_entrypoint.py`
  - E2E continue path: `tests/test_bootstrap_persistence_e2e.py`

## Validation snapshot

- Full suite: `python3 -m pytest -q`
- Result on this branch: `3948 passed, 3 skipped`
