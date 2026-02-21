# Governance Invariants (DoD)

This checklist captures non-negotiable governance invariants that must remain true.
Any change violating one item is a regression.

## Control Plane / Start

- [ ] `/start` must call only read-only diagnostics helpers.
- [ ] `diagnostics/start_preflight_persistence.py` must not exist.
- [ ] Diagnostics must not write workspace/index/session artifacts.

Evidence:
- `start.md`
- `diagnostics/start_preflight_readonly.py`
- `tests/test_start_entrypoint_contract.py`
- `tests/test_start_preflight_persistence.py`
- `tests/architecture/test_diagnostics_control_plane_guards.py`

## Repo Identity / Resolution

- [ ] Repo root resolution is git-evidence-only (`git rev-parse --show-toplevel`).
- [ ] No CWD fallback, no parent-walk, no `.git` presence heuristic for identity.
- [ ] Unresolved / fingerprint-missing state must not expose `repo_root`.

Evidence:
- `governance/context/repo_context_resolver.py`
- `governance/application/use_cases/start_persistence.py`
- `tests/architecture/test_repo_identity_guards.py`
- `tests/test_start_persistence_use_case.py`

## Workspace Ready Gate

- [ ] Workspace readiness is committed by kernel gate only.
- [ ] Gate uses lock dir (`workspaces/<fp>/locks/workspace.lock/`).
- [ ] Gate writes `marker.json` and `evidence/repo-context.resolved.json`.
- [ ] Session pointer is updated atomically.

Evidence:
- `governance/infrastructure/workspace_ready_gate.py`
- `governance/application/use_cases/orchestrate_run.py`
- `tests/test_engine_orchestrator.py`
- `tests/test_verification_suite.py`

## Phase Routing / Ticket Guard

- [ ] Phase routing is evidence/persisted-state driven and monotonic.
- [ ] Phase 2/3 progression requires committed workspace-ready gate.
- [ ] Ticket/task prompts are not allowed before phase 4.
- [ ] Phase 4 remains planning-only (code-output requests blocked).

Evidence:
- `governance/application/use_cases/phase_router.py`
- `governance/application/use_cases/orchestrate_run.py`
- `tests/test_verification_suite.py`
- `tests/test_engine_orchestrator.py`

## Persistence Policy (Phase-Coupled)

- [ ] Persistence decisions are centralized in policy (`allowed` vs `blocked`).
- [ ] Workspace-memory decisions require phase 5 approval + confirmation evidence.
- [ ] Pipeline mode cannot satisfy confirmation flow; must fail closed.
- [ ] Repository writer guards enforce policy even on direct calls.

Evidence:
- `governance/application/policies/persistence_policy.py`
- `governance/infrastructure/persist_confirmation_store.py`
- `governance/infrastructure/workspace_memory_repository.py`
- `tests/test_persistence_policy.py`
- `tests/test_persist_confirmation_store.py`
- `tests/test_workspace_memory_repository.py`
- `tests/test_engine_orchestrator.py`

## Forbidden Regression Patterns

- [ ] No `_unresolved` workspace write paths.
- [ ] No direct `open(..., 'w')` / `Path.write_text(...)` in protected diagnostics/control-plane files.
- [ ] No `shlex.split(...)` command re-splitting for governance command profiles.
- [ ] `Path.resolve()` usage remains allowlisted by architecture guards.

Evidence:
- `tests/architecture/test_diagnostics_control_plane_guards.py`
- `tests/architecture/test_import_rules.py`
- `tests/test_validate_governance.py`

## Canonical Reason Codes (must remain registered)

Persistence and gating reasons must stay present in:
- `governance/domain/reason_codes.py`
- `diagnostics/reason_codes.registry.json`
- `governance/engine/_embedded_reason_registry.py`

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

Cross-field validators in `governance/engine/session_state_invariants.py` enforce:

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
- `governance/engine/session_state_invariants.py`
- `tests/test_session_state_schema.py`
