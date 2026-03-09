# Governance Release Readiness

This document is the operator-facing evidence map for release readiness.
Authoritative runtime truth remains in kernel code, schemas, and tests.

## Acceptance Baseline

- `/continue` materializes kernel-owned state only.
- Free-text (`go`, `weiter`, `proceed`, `mach weiter`) remains chat-only.
- `active_gate`, `next_gate_condition`, `gates_blocked`, and `next` are derived from one evaluation round.
- Exactly one final `Next action:` line is emitted.
- `next=5.3` is treated as an intermediate route target in readout.
- `phase_transition_evidence` controls jump eligibility to Phase 6.
- P5 review evidence auto-propagates to `Gates.P5-Architecture` and `Gates.P5.3-TestQuality`.
- `Gates.P5.5-TechnicalDebt` is always checked for Phase 6 entry (`approved` or `not-applicable`).
- Phase 6 review status is visible via `iteration`, `min`, `max`, `delta`, and `implementation_review_complete`.
- `/review-decision` is the mutating rail for Phase 6 final review decisions (`approve`, `changes_requested`, `reject`).

## Coverage Matrix (B1-B14 / C1-C4)

| Area | Contract | Primary Evidence |
| --- | --- | --- |
| B1 | no stale `next_gate_condition` after gate advance | `tests/test_phase_kernel_contracts.py` |
| B2/B3/B7 | `/continue` guidance not over-broad | `tests/test_session_reader.py` |
| B4/C3 | free-text cannot trigger authoritative writes | `tests/test_free_text_guard.py` |
| B5 | draft vs persisted state separation | `tests/test_session_reader.py`, `tests/test_phase5_plan_record_persist.py` |
| B6 | Phase 5 exit logic as primary gate condition | `tests/test_phase_kernel_contracts.py` |
| B8-B12 | gate propagation and consistency protections | `tests/test_session_state_helpers.py`, `tests/test_session_reader.py` |
| B13 | Phase 6 loop visibility and next-action behavior | `tests/test_session_reader.py` |
| B14 | jump evidence and prerequisite enforcement | `tests/test_phase_kernel_contracts.py`, `tests/test_gate_evaluator_p6_prerequisites.py` |
| C1/C2/C4 | reason-code parity and blocked reason governance | `tests/test_reason_registry_blocked_coverage.py`, `tests/test_reason_catalog_parity.py` |

## Cross-OS Compatibility Matrix

| Domain | Linux | macOS | Windows | Evidence |
| --- | --- | --- | --- | --- |
| Installer smoke | pass | pass | pass | CI `Test Installer on *` |
| Governance E2E | pass | pass | pass | CI `Governance E2E Flow (*)` |
| Path normalization and quoting | pass | pass | pass | `tests/unit/test_preflight_tool_helpers.py`, `tests/test_session_reader.py` |
| Deterministic config patching | pass | pass | pass | `tests/test_installer_flow.py`, `tests/test_installer_metadata_filter.py` |

## Model Identity Matrix (Opus/Codex)

| Scenario | Expected | Evidence |
| --- | --- | --- |
| Opus + trusted binding + explicit context limit | allowed (audit-trusted) | `tests/test_model_identity_service.py` |
| Codex + trusted binding + explicit context limit | allowed (audit-trusted) | `tests/test_model_identity_service.py` |
| Missing trusted binding in pipeline | blocked | `tests/test_model_identity_service.py` |
| Missing explicit context limit in pipeline | blocked | `tests/test_model_identity_service.py` |
| Unknown model id in pipeline | fail-closed blocked | `tests/test_model_identity_service.py` |
| Advisory-only sources (`process_env`, `llm_context`) | never audit-trusted | `tests/test_model_identity.py` |

## Test Matrix (E1-E6 + Extensions)

| Bucket | Coverage |
| --- | --- |
| E1 Governance contracts | `tests/test_phase_kernel_contracts.py`, `tests/test_session_reader.py` |
| E2 Rails contracts | `tests/test_continue_md_contract.py`, `tests/test_ticket_md_contract.py`, `tests/test_plan_md_contract.py` |
| E3 Persistence contracts | `tests/test_phase4_intake_persist.py`, `tests/test_phase5_plan_record_persist.py` |
| E4 Reason/catalog parity | `tests/test_reason_code_usage_guard.py`, `tests/test_reason_registry_blocked_coverage.py`, `tests/test_reason_catalog_parity.py` |
| E5 Model identity | `tests/test_model_identity.py`, `tests/test_model_identity_service.py` |
| E6 Cross-OS installer/E2E | CI workflows + `tests/test_installer_*` + release gate jobs |

## Release Checklist

- Governance test suite green (`pytest -m governance`).
- PR checks green for `Validate Governance Files`, `Governance E2E Flow`, and installer matrix.
- No stale gate/readout divergence in snapshots.
- Free-text guard behavior validated.
- Model identity matrix (Opus/Codex) validated with fail-closed negatives.
- Rails docs and operator docs updated for `/continue`, `/ticket`, `/plan`, `/review-decision` semantics.
