# F100 Completion Gate

Generated: 2026-03-19

## Scope

This record defines the hard completion gate for F100 final-state closure.

## Required Final-State Invariants

- Runtime authority: `governance_runtime/**` must have zero `governance.*` import edges.
- Legacy bridge purity: legacy bridge files must not contain active logic.
- Installer single source: `governance_runtime/install/install.py` is canonical; root `install.py` is a thin delegator.
- Contract liveness: no live contract metadata may use `planned`/`TBD`; archived contracts must be explicitly archived.
- Legacy compatibility surface: frozen and controlled by `governance_spec/migrations/R10_Final_State_Proof.md`.
- Legacy authority finalization: `governance/` is compatibility-only under local root and not an active command-surface runtime target.
- Install layout finalization: config root holds `commands/`, `plugins/`, `workspaces/`, `bin/`; local root holds `governance_runtime/`, `governance_content/`, `governance_spec/`, `governance/`, `VERSION`.
- Command surface finalization: exactly 8 canonical rails in `opencode/commands/` and no forbidden runtime payload targets under `commands/governance`, `commands/cli`, `commands/docs`, `commands/scripts`, `commands/templates`.
- Workspace-only log write targets: no `commands/logs` write fallback in runtime logging paths.
- README and quickstart UX completion: governance-content user docs must be substantive and canonical-command aligned.
- Repo hygiene: cache/test junk, unclassified backlog notes, and redundant raw proof dumps are excluded from active tree.
- Archive boundaries: historical migration/governance docs are archived and excluded from active policy surfaces.

## Canonical Gate Suites

- `tests/conformance/test_f100_runtime_purity_gate.py`
- `tests/conformance/test_f100_workspace_logs_only.py`
- `tests/conformance/test_contract_liveness_conformance.py`
- `tests/conformance/test_installer_ssot_conformance.py`
- `tests/conformance/test_r10_final_state_proof.py`
- `tests/conformance/test_r10_final_readiness_gate.py`
- `tests/conformance/test_r12_legacy_passive_finalization.py`
- `tests/conformance/test_readme_ux_completion.py`
- `tests/conformance/test_repo_hygiene_no_python_cache_artifacts.py`
- `tests/conformance/test_repo_hygiene_no_unclassified_backlog_docs.py`
- `tests/conformance/test_repo_hygiene_no_redundant_proof_dumps.py`
- `tests/conformance/test_repo_hygiene_archive_boundaries.py`
- `tests/conformance/test_repo_hygiene_cleanup_decision_log.py`
- `tests/conformance/test_layout_conformance.py`
- `tests/conformance/test_r16_final_claim_conformance.py`

## Completion Condition

F100 is complete only when all canonical gate suites pass and no invariant drift is detected.
