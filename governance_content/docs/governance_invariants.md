# Governance Invariants (DoD)

This checklist captures non-negotiable governance invariants that must remain true.
Any change violating one item is a regression.

SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance_runtime/kernel/*` is the canonical control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.

## Control Plane / Bootstrap

- [ ] Bootstrap must call only read-only governance helpers.
- [ ] `governance_runtime/bootstrap_preflight_persistence.py` must not exist.
- [ ] Diagnostics must not write workspace/index/session artifacts.

Evidence:
- `BOOTSTRAP.md`
- `governance_runtime/entrypoints/bootstrap_preflight_readonly.py`
- `tests/test_bootstrap_entrypoint_contract.py`
- `tests/test_bootstrap_preflight_persistence.py`
- `tests/architecture/test_governance_control_plane_guards.py`

## Repo Identity / Resolution

- [ ] Repo root resolution is git-evidence-only (`git rev-parse --show-toplevel`).
- [ ] No CWD fallback, no parent-walk, no `.git` presence heuristic for identity.
- [ ] Unresolved / fingerprint-missing state must not expose `repo_root`.

Evidence:
- `governance_runtime/context/repo_context_resolver.py`
- `governance_runtime/application/use_cases/bootstrap_persistence.py`
- `tests/architecture/test_repo_identity_guards.py`
- `tests/test_bootstrap_persistence_use_case.py`

## Workspace Ready Gate

- [ ] Workspace readiness is committed by kernel gate only.
- [ ] Gate uses lock dir (`workspaces/<fp>/locks/workspace.lock/`).
- [ ] Gate writes `marker.json` and `evidence/repo-context.resolved.json`.
- [ ] Session pointer is updated atomically.

Evidence:
- `governance_runtime/infrastructure/workspace_ready_gate.py`
- `governance_runtime/application/use_cases/orchestrate_run.py`
- `tests/test_engine_orchestrator.py`
- `tests/test_verification_suite.py`

## Phase Routing / Ticket Guard

- [ ] Phase routing is evidence/persisted-state driven and monotonic.
- [ ] Phase 2/3 progression requires committed workspace-ready gate.
- [ ] Ticket/task prompts are not allowed before phase 4.
- [ ] Phase 4 remains planning-only (code-output requests blocked).

Evidence:
- `governance_runtime/kernel/phase_kernel.py`
- `${COMMANDS_HOME}/phase_api.yaml`
- `governance_runtime/application/use_cases/orchestrate_run.py`
- `tests/test_verification_suite.py`
- `tests/test_engine_orchestrator.py`

## Persistence Policy (Phase-Coupled)

- [ ] Persistence decisions are centralized in policy (`allowed` vs `blocked`).
- [ ] Workspace-memory decisions require phase 5 approval + confirmation evidence.
- [ ] Pipeline mode cannot satisfy confirmation flow; must fail closed.
- [ ] Repository writer guards enforce policy even on direct calls.

Evidence:
- `governance_runtime/application/policies/persistence_policy.py`
- `governance_runtime/infrastructure/persist_confirmation_store.py`
- `governance_runtime/infrastructure/workspace_memory_repository.py`
- `tests/test_persistence_policy.py`
- `tests/test_persist_confirmation_store.py`
- `tests/test_workspace_memory_repository.py`
- `tests/test_engine_orchestrator.py`

## Forbidden Regression Patterns

- [ ] No `_unresolved` workspace write paths.
- [ ] No direct `open(..., 'w')` / `Path.write_text(...)` in protected runtime/control-plane files.
- [ ] No `shlex.split(...)` command re-splitting for governance command profiles.
- [ ] `Path.resolve()` usage remains allowlisted by architecture guards.

Evidence:
- `tests/architecture/test_governance_control_plane_guards.py`
- `tests/architecture/test_import_rules.py`
- `tests/test_validate_governance.py`

## Canonical Reason Codes (must remain registered)

Persistence and gating reasons must stay present in:
- `governance_runtime/domain/reason_codes.py`
- `governance_runtime/reason_codes.registry.json`
- `governance_runtime/engine/_embedded_reason_registry.py`

Critical codes:
- `BLOCKED-REPO-IDENTITY-RESOLUTION`
- `BLOCKED-WORKSPACE-PERSISTENCE`
- `BLOCKED-STATE-OUTDATED`
- `INTERACTIVE-REQUIRED-IN-PIPELINE`
- `PERSIST_CONFIRMATION_REQUIRED`
- `PERSIST_CONFIRMATION_INVALID`
- `PERSIST_DISALLOWED_IN_PIPELINE`
- `PERSIST_PHASE_MISMATCH`
- `PERSIST_GATE_NOT_APPROVED`

Evidence:
- `tests/test_reason_code_registry.py`
- `tests/test_reason_registry_blocked_coverage.py`
- `tests/test_reason_payload_schema_selfcheck.py`

## Release Gate

Before merge, run:

```bash
python3 -m pytest -q
```

Expected: full suite green (except explicitly skipped tests).

## SESSION_STATE Invariants

Cross-field validators in `governance_runtime/engine/session_state_invariants.py` enforce:

- [ ] When the session is in a blocked state, `Next` starts with `BLOCKED-`.
- [ ] `ConfidenceLevel < 70` requires `Mode` to be `DRAFT` or `BLOCKED`.
- [ ] If `ProfileSource=ambiguous`, the session is in a blocked state.
- [ ] Reason codes require `Diagnostics.ReasonPayloads` to be present.
- [ ] `OutputMode=ARCHITECT` requires `DecisionSurface` to exist.
- [ ] Loaded rulebooks require corresponding load evidence.
- [ ] Loaded addons require corresponding `AddonsEvidence`.
- [ ] Canonical path fields must not contain forbidden patterns (drive prefixes, backslashes, parent traversal).
- [ ] Canonical path fields must not be degenerate (single drive letter, drive root, single segment without variable).
- [ ] `P5-Architecture=approved` requires `ArchitectureDecisions` with at least one `Status=approved` entry.
- [ ] Phase 5/6 code-producing steps require upstream gates to be in allowed state.
- [ ] Gate approval is blocked when `GateArtifacts.Provided` has `missing` items.

Evidence:
- `governance_runtime/engine/session_state_invariants.py`
- `tests/test_session_state_schema.py`
