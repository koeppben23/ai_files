# Backend Python Governance Profile

This document defines **backend Python (FastAPI/Flask/Django/service backends)** profile rules.
It is applied **in addition** to the Core Rulebook (`rules.md`) and the Master Prompt (`master.md`).

## Intent (binding)

Enforce deterministic, evidence-backed backend Python engineering with fail-closed quality gates and production-safe operational defaults.

## Scope (binding)

Backend Python business logic, API/service boundaries, schema and migration safety, deterministic tests, and runtime reliability checks.

## Activation (binding)

This profile applies when backend-python stack evidence is selected by governance profile detection (explicit user choice or deterministic discovery).

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
For backend-python behavior, this profile governs stack-specific rules and activated addons/templates may refine within profile constraints.

## Phase integration (binding)

- Phase 2: discover backend-python stack/tooling and required addon contracts.
- Phase 4: apply backend-python planning/execution constraints.
- Phase 5/6: verify architecture, test quality, and rollback safety via concrete evidence.

## Evidence contract (binding)

- No claim without evidence.
- Every non-trivial claim (for example tests green, static clean, no drift) MUST map to `SESSION_STATE.BuildEvidence.items[]`.
- Missing/stale evidence MUST result in `NOT_VERIFIED` semantics for the affected claim.
- Recovery guidance MUST reference existing commands/scripts only.

## Shared Principal Governance Contracts (Binding)

To keep this profile focused on Python-specific engineering behavior, shared principal governance contracts are modularized into advisory rulebooks:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior for `backend-python` profile:

- At code/review phases (Phase 4+), these shared contracts MUST be loaded as advisory governance contracts.
- When loaded, record in:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- If one of these shared rulebooks is unavailable, emit a warning, mark affected claims as
  `not-verified`, and continue conservatively without inventing evidence.

## Tooling (binding)

- Use repository-native Python tooling first (for example `pytest`, `ruff`, `mypy`, `uv`, `poetry`, `pip-tools`, `alembic`).
- Prefer pinned and reproducible invocation forms (lockfile/workflow-defined commands).
- When required tooling is unavailable in host constraints, emit deterministic recovery commands and preserve fail-closed gate behavior.

### Recommended deterministic command order

1. format/lint (`ruff check`, project formatter if configured)
2. type checks (`mypy`/configured checker when present)
3. targeted tests, then full test suite
4. migration checks (if schema layer changed)

## Python-specific quality contracts (binding)

### 1) Contract and boundary safety

- API schema changes MUST be validated against declared contracts and consumer impact.
- Request/response models MUST not silently widen types or nullability without explicit migration/compatibility rationale.
- Cross-boundary DTO/schema changes require explicit backward-compatibility evidence.

### 2) Deterministic test quality

- Tests MUST avoid nondeterministic timing/network dependencies unless explicitly mocked or isolated.
- Async code paths MUST include explicit async test coverage where behavior differs from sync paths.
- Flaky retries MUST NOT be used to mask nondeterminism.

### 3) State, migrations, and rollback

- Migration-impacting changes MUST include forward + rollback/backout evidence.
- Data-shape contract changes MUST include compatibility and deployment-order notes.
- If rollback safety cannot be demonstrated, gate outcome cannot be `ready-for-pr`.

### 4) Security and operational hygiene

- Secrets/tokens MUST NOT be introduced in source, tests, fixtures, or logs.
- Input validation and authorization behavior changes require explicit negative-path evidence.
- Logging changes MUST avoid PII/secret leakage and preserve troubleshooting utility.

## Examples (GOOD/BAD)

### GOOD

- "`tests green`" claim linked to concrete `BuildEvidence` test runs with stable command/version context.
- API model change includes schema diff evidence + compatibility note + updated tests.
- Migration change includes forward validation and rollback/backout strategy evidence.

### BAD

- Claiming "no drift" without hash/evidence mapping in session diagnostics.
- Relying on local unstated interpreter/package versions for gate claims.
- Marking `ready-for-pr` while migration rollback evidence is missing.

## Troubleshooting

### `NOT_VERIFIED` due to missing evidence

- Re-run the relevant deterministic command(s) from repo tooling and ingest output evidence.
- Ensure evidence items include claim mapping and fresh timestamps.

### Host cannot run required Python toolchain

- Emit one primary recovery command for the operator.
- Keep claim status `NOT_VERIFIED` until concrete evidence is ingested.

### Ambiguous stack/profile detection

- Stay fail-closed until profile selection is explicit or deterministic evidence resolves ambiguity.
- Do not mix backend-python with unrelated stack profile constraints in one gate decision.

---

Copyright (c) 2026 Benjamin Fuchs
All rights reserved.
