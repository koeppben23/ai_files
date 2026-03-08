<!-- rail-classification: CONSTRAINT-SET, CROSS-PHASE -->

This document defines stack-agnostic technical, quality, evidence, and output rules.
Operator guidance semantics (phases, session-state, hybrid mode, priorities, gates) are in `master.md`.
Runtime routing and control-plane behavior are kernel-owned (`phase_api.yaml` + `governance/kernel/*`).

Authority boundary: Schemas, validators, and kernel code (`governance/kernel/*`) are the runtime SSOT. This Markdown provides constraint intent and interpretation boundaries only. When in doubt, follow the schema/validator/kernel reference.

Default: any section labeled Kernel-Enforced or Binding is reference-only; the SSOT (`governance/kernel/*` and `governance/assets/schemas/*`) behavior wins.
Governance release stability is normatively defined by `STABILITY_SLA.md` and is release-blocking when unmet.

State-machine alignment:
- Runtime orchestration logic is in `governance/engine/*` and response projection in `governance/render/*`.
- This file states constraints and evidence intent, not runtime implementation details.
- If a conflict is suspected, defer to kernel/schema sources (`governance/kernel/*`, `governance/assets/schemas/*`) and report it.

Schema IDs are versioned (`schema: governance.<area>.<name>.v1`).
Doc-lint standard: `docs/governance/doc_lint.md`.

## Authority Index

All routing, validation, transitions, state shape, and presentation are kernel- and schema-owned.
This section is the single consolidated reference; individual sections do not repeat SSOT pointers.

| Area | SSOT source |
|------|-------------|
| Routing / validation / transitions | `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*` |
| Session-state shape and invariants | `SESSION_STATE_SCHEMA.md` and `governance/assets/schemas/*` |
| Response envelope and presentation | `governance/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json` |
| Blocked reason catalog | `governance/assets/reasons/blocked_reason_catalog.yaml` |
| Persistence artifacts | `governance/assets/config/persistence_artifacts.yaml` |
| Build verification and evidence | `docs/governance/governance_schemas.md` |
| Rulebook data (machine-readable) | `rulesets/core/rules.yml` |

---

## 0. Governance Scope Model

If the repository is a monorepo or contains multiple stacks/components, establish a **Component Scope** before any code-producing work.

Component Scope is a bounded set of repo-relative paths (folders) that define ownership and limits.

Binding rules:
- If code generation is requested and Component Scope is not explicit, kernel may return a blocked outcome and request clarification.
- If Component Scope is provided, recommendations and profile detection prefer signals inside those paths.
- The response records component scope in session state; see `SESSION_STATE_SCHEMA.md`.

### Working Set & Touched Surface

To reduce re-discovery and maximize determinism, Phase 2 records working set and touched surface.
See `SESSION_STATE_SCHEMA.md` for fields.

Rules:
1. All planning and reviews are grounded in the Working Set unless evidence requires expansion.
2. If the plan expands beyond the Working Set, update `TouchedSurface` accordingly.
3. Touched surface governs review depth, security sanity checks, and Fast Path eligibility; see `${COMMANDS_HOME}/phase_api.yaml`.

---

## 3. Archive Artifacts & Technical Access

### Path Expression Hygiene

Path expression rules are kernel-owned. See `governance/engine/session_state_invariants.py` and `SESSION_STATE_SCHEMA.md`.

---

## 4. Profile Detection & Rulebook Activation

In ambiguous cases, proceed only in planning/analysis mode (Phase 4) or switch to BLOCKED and request the profile before code-producing work.
The detected profile is recorded as an assumption in session state, including evidence (files/paths) used.

Unambiguous rulebook auto-load:
- When profile detection is unambiguous and host filesystem access is available, load core/profile rulebooks from canonical installer paths.
- In that case, the workflow does not ask the operator to provide/paste rulebook files.

### Ambiguity Handling

Ambiguity handling, profile ranking, and blocked behavior are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Active Profile Traceability

Active profile tracking is kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Canonical Rulebook Precedence

Precedence rules are kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/RESPONSIBILITY_BOUNDARY.md`.

Scope note:
- This precedence order governs AI guidance text only.
- Runtime routing/execution/validation precedence is controlled by `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*`.

### Addon Surface Ownership Matrix

Addon surface ownership and conflict handling are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Capability-First Activation

Activation decisions and capability handling are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

---

## 6. Evidence Rules

### Evidence Ladder

Evidence precedence is kernel-owned; see `docs/governance/RESPONSIBILITY_BOUNDARY.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### Strict Evidence Mode (Default)

- If evidence is not possible, the workflow explicitly states:
  > "Not provable with the provided artifacts."

Stable reference alternatives and placement rules are schema- and kernel-owned; see `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### Gate Artifact Completeness

Gate artifact completeness is kernel- and schema-owned; see `SESSION_STATE_SCHEMA.md`.

### Contract & Schema Evolution Gate

Contract/schema gate details are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

---

## 6.x Phase Semantics

Phase semantics are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

---

## 7.x Fast Path Awareness

Fast Path behavior is kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.
Fast Path is an efficiency optimization, not a correctness shortcut.

---

## 7.3 Presentation Advisory (Consolidated)

The following presentation conventions are renderer/schema-owned.
Exact envelope/format: `governance/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json` and `docs/governance/governance_schemas.md`.

Operative rules:
1. Responses expose exactly one actionable next step.
2. One primary blocker is surfaced first; recovery stays deterministic.
3. Required-gate missing evidence is treated as blocked, not warn.
4. Presentation mode does not change gate/evidence semantics.

Conversational fixtures: `governance/assets/catalogs/UX_INTENT_GOLDENS.json`.
Session-state formatting: `SESSION_STATE_SCHEMA.md`.

---

## 7.4 Architecture Decision Output Template

Non-trivial architecture proposals present options, trade-offs, recommendation, and missing evidence.
Exact template is advisory or schema-owned; see `docs/governance/governance_schemas.md`.

## 7.5 Change Matrix

Cross-cutting changes require a change matrix in planning/review.
Exact matrix schema/template: `docs/governance/governance_schemas.md`.

### 7.6 Security, Privacy & Secrets Sanity Checks

They are **not** a replacement for a full security review.

Binding trigger:
Touched-surface security flags are kernel- and schema-owned; see `SESSION_STATE_SCHEMA.md`.

Minimum checks and reporting are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### 7.7 Change Matrix Verification

Verification rules and blocked behavior are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Mandatory Review Matrix (MRM)

MRM structure, risk tiers, and evidence requirements are schema- and kernel-owned; see `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### Gate Review Scorecard

Scorecard format and gate evaluation rules are schema- and kernel-owned; see `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### Cross-Repository Impact Enforcement

Cross-repo impact rules and required fields are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Review-of-Review Consistency Check

Consistency-check requirements and output format are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

## 7.8 Business Logic & Testability Design Contract

If the repo already defines an appropriate domain type/value object for the value, use it.
External boundary layers (controllers/handlers/adapters) do not contain business rules; they may validate input shape and map to domain models.

Output obligation (planning + Phase 5) is schema- and kernel-owned; see `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

## 7.9 Test Design Contract

Test design constraints and determinism expectations are schema- and kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

## 7.10 Conventional Branch/Commit Contract

Branch/commit naming rules are tooling-owned.
See `docs/releasing.md` and repository tooling (if present).

Governance-change PR operator-impact note (recommended):
- For pull requests that change governance rulebooks/contracts, PR body should include a compact section.

## 7.11 Operator Reload Contract

Reload execution, state updates, and continuation behavior are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Bootstrap Re-invocation Loop Guard

Bootstrap re-invocation loop guard behavior is kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

## 7.12 Operator Explain Contracts

Explain-command inputs, read-only guarantees, and output shape are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

## 7.13 Proof-Carrying Explain Output

Explain output shape is kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

## 7.14 Evidence Scope and Ticket Isolation Guards

Evidence isolation rules are kernel- and schema-owned; see `SESSION_STATE_SCHEMA.md`.

## 7.15 Deterministic Activation Delta Contract

Activation delta invariants are kernel-owned; see `governance/engine/session_state_invariants.py`.

## 7.16 Toolchain Pinning Evidence Policy

Toolchain evidence policy is kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

## 7.17 Rulebook Load Evidence Gate

Rulebook load evidence gate is kernel- and schema-owned; see `SESSION_STATE_SCHEMA.md`.

---

## 8. Traceability

Traceability format is schema-owned; see `docs/governance/governance_schemas.md`.

### Ticket Record

Ticket record format and fields are schema-owned; see `SESSION_STATE_SCHEMA.md` and `docs/governance/governance_schemas.md`.

### Business Rules Traceability

Business rules traceability, BR register shape, coverage reporting, and gap handling are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Business Rules Inventory File

Business rules inventory location, format, lifecycle, and persistence are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/config/persistence_artifacts.yaml`.

### Decision Pack File

Decision Pack location, format, lifecycle, and persistence are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/config/persistence_artifacts.yaml`.

### RepoMapDigest File

RepoMapDigest location, format, lifecycle, and persistence are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/config/persistence_artifacts.yaml`.

---

## 9. BuildEvidence

BuildEvidence semantics, status handling, and evidence mapping are kernel- and schema-owned; see `SESSION_STATE_SCHEMA.md` and `${COMMANDS_HOME}/phase_api.yaml`.

---

## 10. Test Quality

Test-quality expectations and gate requirements are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

Profile & scope override handling:
Override fields and recording requirements are kernel- and schema-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

---
