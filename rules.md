This document defines **stack-agnostic, non-negotiable** technical, quality, evidence, and output rules.
Operator guidance semantics (phases, session-state presentation, hybrid mode, priorities, gates) are described in the **Master Prompt** (`master.md`). Runtime routing and control-plane behavior are kernel-owned (`phase_api.yaml` + `governance/kernel/*`).

Authority boundary: Schemas, validators, and kernel code are authoritative. This Markdown is not SSOT and does not define runtime truth. It provides constraint intent and allowable interpretation boundaries only, and must point to authoritative sources for any behavior, format, or state. When in doubt, follow the schema/validator/kernel reference.

Default: any section labeled Kernel-Enforced or Binding is reference-only; the SSOT/kernel behavior is authoritative.
Governance release stability is normatively defined by `STABILITY_SLA.md` and is release-blocking when unmet.


State-machine alignment note:
- Runtime orchestration logic is implemented in `governance/engine/*` and response projection logic in `governance/render/*`.
- This file states core constraints and evidence intent, not low-level runtime implementation details.
- If a conflict is suspected, defer to the authoritative kernel/schema sources and report it.

This Core Rulebook is:
- **secondary to the Master Prompt for AI guidance semantics**
- Schema IDs are versioned (`schema: governance.<area>.<name>.v1`).
 - Compact presentation schema: `governance.compact_mode.v1` (optional).

Doc-lint standard: `docs/governance/doc_lint.md`.

## Authority Index (Rail-only Guidance - See rulesets/core/rules.yml for authoritative data)

Authoritative sources by area (see rulesets/core/rules.yml for machine-readable authoritative data):
- Routing/validation/transitions: `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*`
- Session-state shape and invariants: `SESSION_STATE_SCHEMA.md` and `governance/assets/schemas/*`
- Response envelope and presentation shape: `governance/RESPONSE_ENVELOPE_SCHEMA.json`
- Blocked reason catalog: `governance/assets/reasons/blocked_reason_catalog.yaml`
- Persistence artifacts and targets: `governance/assets/config/persistence_artifacts.yaml`
- Build verification and evidence rules: `docs/governance/governance_schemas.md`

---

## 0. Governance Scope Model
If the repository is a monorepo or contains multiple stacks/components, the workflow MUST establish a **Component Scope**
before any code-producing work.

Component Scope is a bounded set of repo-relative paths (folders) that define ownership and limits.

Binding rules:
- If code generation is requested and **Component Scope is not explicit**, kernel may return a blocked outcome and request clarification.
- If Component Scope is provided, recommendations and profile detection prefer signals inside those paths.
- The response records component scope in session state (schema-owned).

### 2.x Working Set & Touched Surface (Binding once Phase 2 completed)

To reduce re-discovery and maximize determinism, Phase 2 should record working set and touched surface.
See `SESSION_STATE_SCHEMA.md` for authoritative fields.

Rules:
1) All planning and reviews MUST be grounded in the Working Set unless evidence requires expansion.
2) If the plan expands beyond the Working Set, the workflow MUST update `TouchedSurface` accordingly.

Additional binding:
3) Touched surface governs review depth, security sanity checks, and Fast Path eligibility (kernel-owned).

## 3. Archive Artifacts & Technical Access


### 3.3 Path Expression Hygiene (Kernel-Enforced)

Path expression rules are kernel-owned. See `governance/engine/session_state_invariants.py` and `SESSION_STATE_SCHEMA.md`.

---

In that case, proceed only in planning/analysis mode (Phase 4) or switch to BLOCKED and request the profile before any code-producing work.
The detected profile must be recorded as an **assumption** in the session state, including evidence (files/paths) used.

Deterministic Java default is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

Unambiguous rulebook auto-load (Rail-only Guidance):
- When profile detection is unambiguous and host filesystem access is available, load core/profile rulebooks from canonical installer paths.
- In that unambiguous case, the workflow MUST NOT ask the operator to provide/paste rulebook files.

Deterministic detection hints are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

### 4.4 Ambiguity Handling (Policy)

Ambiguity handling, profile ranking, and blocked behavior are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

### 4.5 Active Profile Must Be Traceable

Active profile tracking is kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

### 4.6 Canonical Rulebook Precedence (Kernel-Enforced)

Stable anchor IDs are schema- and kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

Precedence rules are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/RESPONSIBILITY_BOUNDARY.md`.

Scope note (Rail-only Guidance):
- This precedence order governs AI guidance text only.
- Runtime routing/execution/validation precedence is controlled exclusively by `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*`.

SSOT clarification, addon class behavior, and conflict handling are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/RESPONSIBILITY_BOUNDARY.md`.

### 4.7 Required-Addon Emergency Override (Policy)


### 4.8 Addon Surface Ownership Matrix (Kernel-Enforced)

Addon surface ownership fields and conflict handling are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/reasons/blocked_reason_catalog.yaml`.

### 4.9 Capability-First Activation (Policy)

Activation decisions and capability handling are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`.

---


### 6.0 Evidence Ladder (Kernel-Enforced)

Evidence precedence is kernel-owned. See `docs/governance/RESPONSIBILITY_BOUNDARY.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### 6.1 Strict Evidence Mode (Default)

- if evidence is not possible, the workflow MUST explicitly say:
  > "Not provable with the provided artifacts."

**Stable reference alternatives and placement rules are schema- and kernel-owned.**
See `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### 6.2 Light Evidence Mode (Explicit Exception Only)

defined in master.md or this rulebook.

### 6.4 Gate Artifact Completeness (Kernel-Enforced)

Gate artifact completeness is kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md`.

## 6.5 Contract & Schema Evolution Gate (MANDATORY)

Contract/schema gate details are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

---


## 6.x Phase Semantics (Policy)

Phase semantics are kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

---


### 7.x Fast Path Awareness (Binding, Non-Bypass)

Fast Path behavior is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

Fast Path is an efficiency optimization, not a correctness shortcut.


### 7.3.1 Unified Next Action Footer (Presentation Advisory)

Responses should expose exactly one actionable next step.
Exact envelope/format is schema-owned. See `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.2 Standard Blocker Output Envelope (Kernel-Enforced)

One primary blocker must be surfaced first, and recovery must remain deterministic.
Exact payload/envelope lives in the blocked-reason catalog and response schema.

### 7.3.3 Cold/Warm Start Banner (Presentation Advisory)

Start mode may be surfaced for operator orientation.
Exact banner rendering is renderer/schema-owned.

### 7.3.4 Confidence + Impact Snapshot (Presentation Advisory)

Responses may include a compact confidence/risk/scope summary.
Exact shape is schema-owned. See `SESSION_STATE_SCHEMA.md` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.5 Quick-Fix Commands for Blockers (Presentation Advisory)

Quick-fix guidance and fields are schema- and kernel-owned.
See `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.6 Architect-Only Autopilot Lifecycle (Policy)

Lifecycle and output mode rules are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

### 7.3.7 Canonical Response Envelope Schema (Presentation Advisory)

- `governance/RESPONSE_ENVELOPE_SCHEMA.json`
- `docs/governance/governance_schemas.md` (schema IDs and drafts)

### 7.3.8 Host Constraint Compatibility Mode (Kernel-Enforced)

Host-constraint response behavior is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

### 7.3.9 SESSION_STATE Formatting Contract (Presentation Advisory)

Session-state formatting and required fields are schema-owned. See `SESSION_STATE_SCHEMA.md`.

### 7.3.10 Bootstrap Preflight Output Contract (Kernel-Enforced)

Preflight output contract is kernel- and schema-owned. See `governance.preflight.v1` in `docs/governance/governance_schemas.md`.

### 7.3.11 Deterministic Status + Next Step Contract (Kernel-Enforced)

Status vocabulary and next-step contracts are kernel- and schema-owned.
See `governance/engine/session_state_invariants.py` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.12 Session Transition Invariants (Kernel-Enforced)

Transition integrity is kernel-enforced.
See `governance/engine/session_state_invariants.py` and `SESSION_STATE_SCHEMA.md`.

### 7.3.13 Smart Retry + Restart Guidance (Kernel-Enforced)

Retry/restart guidance is kernel-owned and may be surfaced to operators.
Canonical fields live in schema/kernel. See `bootstrap_preflight_readonly.py` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.14 Phase Progress + Warn/Blocked Separation (Kernel-Enforced)

Required-gate missing evidence must be treated as blocked, not warn.
Exact projection of phase/gate/progress is schema/kernel-owned.

### 7.3.15 Output Modes (Presentation Advisory)

Hosts may operate in strict or compatibility presentation modes.
Presentation mode must not change gate/evidence semantics.
Exact mode-specific output requirements are schema-owned. See `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.16 Operator-First Brief/Detail Layering (Presentation Advisory)

Brief-first presentation is allowed for operator usability.
It must not suppress blocker-critical content.

### 7.3.17 Post-Start Conversational UX + Language Adaptation (Presentation Advisory)

Post-bootstrap operator UX may be concise, language-adaptive, and presentation-tunable.
Conversational behavior is renderer/catalog-owned.

### 7.3.18 Conversational UX Regression Fixtures (Presentation Advisory)

Conversational fixtures are renderer/catalog-owned.
See `governance/assets/catalogs/UX_INTENT_GOLDENS.json`.

### 7.3.19 Short-Intent Routing for Operator Questions (Presentation Advisory)

Conversational routing and persona behavior are renderer/catalog-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### 7.3.20 Operator Persona Response Modes (Presentation Advisory)

Post-bootstrap operator UX may be concise, language-adaptive, and presentation-tunable.
Conversational routing and persona behavior are renderer/catalog-owned.

### 7.4 Architecture Decision Output Template (Binding when proposing non-trivial architecture)

Non-trivial architecture proposals should present options, trade-offs, recommendation, and missing evidence.
Exact template is advisory or schema-owned. See `docs/governance/governance_schemas.md`.

## 7.5 Change Matrix (MANDATORY)

Cross-cutting changes require a change matrix in planning/review.
Exact matrix schema/template is external. See `docs/governance/governance_schemas.md`.

### 7.6 Security, Privacy & Secrets Sanity Checks (Core, Lightweight)

They are **not** a replacement for a full security review.

Binding trigger:
Touched-surface security flags are kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md`.

Minimum checks and reporting are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

### 7.7 Change Matrix Verification (Binding STOP)

Verification rules and blocked behavior are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

### 7.7.1 Mandatory Review Matrix (MRM) (Core, Binding)

MRM structure, risk tiers, and evidence requirements are schema- and kernel-owned.
See `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### 7.7.2 Gate Review Scorecard (Core, Binding)

Scorecard format and gate evaluation rules are schema- and kernel-owned.
See `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

### 7.7.3 Cross-Repository Impact Enforcement (Core, Binding)

Cross-repo impact rules and required fields are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

### 7.7.4 Review-of-Review Consistency Check (Core, Binding)

Consistency-check requirements and output format are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

## 7.8 Business Logic & Testability Design Contract (Core, Binding)

  If the repo already defines an appropriate domain type/value object for the value, you MUST use it.
- External boundary layers (controllers/handlers/adapters) MUST NOT contain business rules; they MAY validate input shape and map to domain models.

Output obligation (planning + Phase 5) is schema- and kernel-owned.
See `docs/governance/governance_schemas.md` and `${COMMANDS_HOME}/phase_api.yaml`.

## 7.9 Test Design Contract (Core, Binding)

Test design constraints and determinism expectations are schema- and kernel-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

## 7.10 Conventional Branch/Commit Contract (Core, Binding)

Branch/commit naming rules are tooling-owned.
See `docs/releasing.md` and repository tooling (if present).

Governance-change PR operator-impact note (recommended):
- For pull requests that change governance rulebooks/contracts, PR body SHOULD include a compact section:

## 7.11 Operator Reload Contract (Core, Binding)

Reload execution, state updates, and continuation behavior are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

## 7.11.1 Bootstrap Re-invocation Loop Guard (Core, Binding)

Bootstrap re-invocation loop guard behavior is kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/reasons/blocked_reason_catalog.yaml`.

## 7.12 Operator Explain Contracts (Core, Binding)

Explain-command inputs, read-only guarantees, and output shape are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

## 7.13 Proof-Carrying Explain Output (Core, Binding)

Explain output shape is kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

## 7.14 Evidence Scope and Ticket Isolation Guards (Core, Binding)

Evidence isolation rules are kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md`.

## 7.15 Deterministic Activation Delta Contract (Core, Binding)

Activation delta invariants are kernel-owned. See `governance/engine/session_state_invariants.py`.

## 7.16 Toolchain Pinning Evidence Policy (Core, Binding)

Toolchain evidence policy is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

## 7.17 Rulebook Load Evidence Gate (Core, Binding)

Rulebook load evidence gate is kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md` and blocked reason catalog.

---

## 8. Traceability (Core)

Traceability format is schema-owned. See `docs/governance/governance_schemas.md`.

---

### 8.0 Ticket Record (Mini-ADR + NFR Checklist) — REQUIRED in Phase 4 planning

Ticket record format and fields are schema-owned. See `SESSION_STATE_SCHEMA.md` and `docs/governance/governance_schemas.md`.

## 8.1 Business Rules Traceability (Binding when Phase 1.5 executed)

Business rules traceability, BR register shape, coverage reporting, and gap handling are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `docs/governance/governance_schemas.md`.

### 8.x Business Rules Inventory File (Kernel-Managed, Conditional)

Business rules inventory location, format, lifecycle, and persistence are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/config/persistence_artifacts.yaml`.

### 8.y Decision Pack File (Kernel-Managed, Conditional)

Decision Pack location, format, lifecycle, and persistence are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/config/persistence_artifacts.yaml`.

If the file does not exist, non-blocking behavior is kernel-enforced.
See `${COMMANDS_HOME}/phase_api.yaml`.

> **Note:** Non-blocking behavior and failure handling are kernel-enforced.
> See `governance/assets/config/persistence_artifacts.yaml` (artifact: `decision_pack`).

### 8.z RepoMapDigest File (Kernel-Managed, Conditional)

RepoMapDigest location, format, lifecycle, and persistence are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/config/persistence_artifacts.yaml`.

> **Note:** Non-blocking behavior and failure handling are kernel-enforced.
> See `governance/assets/config/persistence_artifacts.yaml` (artifact: `repo_digest`).

## 9. BuildEvidence (Core)

BuildEvidence semantics, status handling, and evidence mapping are kernel- and schema-owned.
See `SESSION_STATE_SCHEMA.md` and `${COMMANDS_HOME}/phase_api.yaml`.

---

## 10. Test Quality (Core, Stack-Neutral)

Test-quality expectations and gate requirements are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

Profile & scope override handling (Rail-only Guidance):
Override fields and recording requirements are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

---

