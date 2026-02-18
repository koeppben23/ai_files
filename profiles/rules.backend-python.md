# Backend Python Governance Profile Rulebook (v1.0)

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
- If a recovery path references a script, that script MUST exist in repository/runtime surface; otherwise fail closed using canonical core reason handling and emit one minimal real command.
- Reason codes are case-sensitive and MUST be carried unchanged (canonical casing) across `reason_payload`, snapshot views, and template lookups.

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
- SHOULD use pinned and reproducible invocation forms (lockfile/workflow-defined commands).
- When required tooling is unavailable in host constraints, emit deterministic recovery commands and preserve fail-closed gate behavior.
- This profile inherits core mode constraints: user-mode operations MUST NOT require writes outside repository/workspace/config boundaries; if required, block with canonical mode-violation handling and recovery.

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

---

## Repo Conventions Lock (Binding)

Before code changes, detect and lock in `SESSION_STATE`:
- Python version and virtual environment strategy (venv/poetry/uv/conda)
- Web framework (FastAPI/Flask/Django/other) and router/middleware conventions
- ORM/data-access pattern (SQLAlchemy/Django ORM/raw SQL/other)
- Migration tool (Alembic/Django migrations/other)
- Test runner and assertion style (pytest/unittest/pytest-bdd)
- Linter/formatter configuration (ruff/black/isort/flake8/mypy)
- Dependency management (pip/poetry/uv/pip-tools)
- Project structure convention (src layout vs flat)

Rule: once detected, these become constraints. If unknown, mark unknown and avoid introducing a new architecture pattern.

---

## Templates Addon (Binding)

For the `backend-python` profile, deterministic generation requires the templates addon:
`rules.backend-python-templates.md`.

Binding:
- At **code-phase** (Phase 4+), the workflow MUST load the templates addon and record it in:
  - `SESSION_STATE.LoadedRulebooks.templates`
- The load evidence MUST include resolved path plus version/digest evidence when available:
  - `SESSION_STATE.RulebookLoadEvidence.templates`
- When loaded, templates are binding defaults; if a template conflicts with locked repo conventions, apply the minimal convention-aligned adaptation and document the deviation.

---

## Addon Policy Classes (Binding)

- Addon class semantics are canonical in `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` and `master.md`; this profile MUST reference, not redefine, those semantics.
- Addon manifests/rulebooks MUST declare `addon_class` explicitly.
- This profile may define Python-specific required-signal logic, but missing-rulebook handling MUST follow canonical policy.

---

## Quality Gates (Hard Fail)

Change fails if any applies:

### PQG-1 Build/Lint Gate
- lint/format/type-check not green

### PQG-2 Contract Gate (if contracts exist)
- API schema drift without explicit approval
- edited generated code

### PQG-3 Architecture Gate
- layer/module boundary violations
- fat route handlers (business logic in API layer)

### PQG-4 Test Quality Gate
- missing behavioral coverage for changed logic
- flaky or nondeterministic tests
- missing negative-path coverage for changed behavior

### PQG-5 Migration Gate (if migrations present)
- migration without rollback/backout evidence
- data-shape change without compatibility assessment

### PQG-6 Operational Gate
- logging/security/auth regression

---

## BuildEvidence Gate (Binding)

Claims like these require evidence snippets in `SESSION_STATE.BuildEvidence`:
- "tests are green"
- "lint/type-check clean"
- "no contract drift"
- "migration validated"

If evidence is missing, status is "not verified" and the change cannot pass Phase 5.3 / 6.

No exceptions.

---

## Definition of Done (Binding)

A backend Python change is **DONE** only if:

- All Quality Gates pass
- All claims are evidence-backed
- No generated code was edited
- Architecture boundaries are intact
- Tests prove behavior, not implementation
- Migration safety is demonstrated (when applicable)
- SESSION_STATE contains BuildEvidence

If any item is missing → **NOT DONE**.

---

## Python-specific Principal Hardening v2 (Binding)

This section defines Python-specific, measurable hardening rules for business and test code.

### PYPH2-1 Risk tiering by touched surface (binding)

The workflow MUST classify changed scope before implementation and gate reviews
using the canonical tiering contract from `rules.risk-tiering.md` (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`).

`PYPH2` adds Python-specific obligations per canonical tier; it does not define a parallel tier system.

### PYPH2-2 Mandatory evidence pack per tier (binding)

For `TIER-LOW` (per canonical tiering), evidence requires:
- lint/type-check pass
- changed-module tests

For `TIER-MEDIUM`, evidence requires:
- lint/type-check pass
- changed-module tests
- at least one negative-path test for changed behavior

For `TIER-HIGH`, evidence requires:
- lint/type-check pass
- changed-module tests
- contract or schema checks (if repo tooling exists)
- one deterministic negative-path test and one deterministic resilience test (retry/idempotency/concurrency as applicable)

### PYPH2-3 Hard fail criteria for principal acceptance (binding)

A Python change MUST be marked `fail` in P5.3/P6 if any applies:

- `PYPH2-FAIL-01`: no evidenceRef for a critical claim
- `PYPH2-FAIL-02`: contract-facing change without negative-path proof
- `PYPH2-FAIL-03`: async/persistence risk change without deterministic resilience proof
- `PYPH2-FAIL-04`: generated code modified by hand
- `PYPH2-FAIL-05`: flaky test behavior detected (nondeterministic timing or uncontrolled I/O)

### PYPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps:

- `WARN-PYTHON-MIGRATION-ROLLBACK-MISSING`: migration change without rollback evidence — recovery: add down-migration and test both directions
- `WARN-PYTHON-ASYNC-DETERMINISM`: async test without deterministic control — recovery: add explicit async mock/fixture control
- `WARN-PYTHON-TYPE-CHECK-SKIPPED`: type checker not available in environment — recovery: install mypy/pyright and run against changed modules

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
- MUST keep claim status `NOT_VERIFIED` until concrete evidence is ingested.

### Ambiguous stack/profile detection

- Stay fail-closed until profile selection is explicit or deterministic evidence resolves ambiguity.
- Do not mix backend-python with unrelated stack profile constraints in one gate decision.

---

Copyright (c) 2026 Benjamin Fuchs
All rights reserved.
