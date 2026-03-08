<!-- rail-classification: GUIDANCE, MULTI-PHASE -->

This file is operator guidance for the governance phase model.
It does not define runtime truth; it references SSOT sources for behavior, format, and state.

SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.

Schema IDs are versioned (`schema: governance.<area>.<name>.v1`).
Doc-lint standard: `docs/governance/doc_lint.md`.

## Authority Index

All routing, validation, transitions, state shape, and presentation are kernel- and schema-owned.
This section is the single consolidated reference; individual phase sections do not repeat SSOT pointers.

| Area | SSOT source |
|------|-------------|
| Routing / validation / transitions | `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*` |
| Session-state shape and invariants | `SESSION_STATE_SCHEMA.md` and `governance/assets/schemas/*` |
| Response envelope and presentation | `governance/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json` |
| Blocked reason catalog | `governance/assets/reasons/blocked_reason_catalog.yaml` |
| Bootstrap gating policy | `governance/assets/config/bootstrap_policy.yaml` |
| Path validation rules | `governance/engine/session_state_invariants.py` |
| Command inventory / tooling policy | `governance/assets/catalogs/tool_requirements.json` |
| Rulebook data (machine-readable) | `rulesets/core/rules.yml` |

---

## Phase Routing Table

All phases are kernel-enforced from `${COMMANDS_HOME}/phase_api.yaml`.
Gate sequencing, transitions, and blocked conditions are kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

| Phase | Name | Key constraint |
|-------|------|----------------|
| 0 | Bootstrap | Conditional; operator must restate bootstrap declaration if blocked |
| 1.2 | Profile Detection | Profile selection is kernel-enforced; persists profile choice in session state |
| 1.3 | Core Rules Activation | Mandatory before every phase >=2; execution constraints in phase_api.yaml |
| 1.4 | Templates & Addons | Addon catalog at `${PROFILES_HOME}/addons/*.addon.yml`; see addon rules below |
| 1.5 | Business Rules Discovery | Conditional; extraction/inventory/persistence are kernel-owned |
| 2 | Repo Discovery | Repo evidence, workspace memory, decision pack; persistence gate mandatory |
| 3A | API Inventory | External artifacts; inputs/outputs/transitions are kernel-owned |
| 3B-1 | API Logical Validation | Spec-level; validation rules in phase_api.yaml |
| 3B-2 | Contract Validation | Spec-to-code; non-blocking conditions in phase_api.yaml |
| 4 | Planning | Deterministic initialization, ticket record, implementation plan, risk review |
| 5 | Review | Review gate only; no implementation output; see Phase 5 rules below |
| 5.3 | Test Quality Review | CRITICAL gate; must pass before proceed to Phase 6 |
| 5.4 | Business Rules Compliance | Only if Phase 1.5 executed |
| 6 | Implementation QA | Self-review gate; prerequisites and verification are kernel-owned |

---

## Phase 0 — Bootstrap

> **BLOCKED — Bootstrap not satisfied**

Terminology:
- **Plan-Gates** are explicit decision gates that control whether code-producing output is described.
- **Evidence-Gates** are evidence prerequisites required to claim a gate outcome; a Plan-Gate may be logically satisfied but still **blocked** if evidence is missing.

Recovery: Operator must restate the bootstrap declaration explicitly.

---

## Global Path Variables

Operator guidance:
- Always express paths using canonical variables in outputs.
- Treat absolute host paths as evidence-only, not canonical.
- Prefer host-side evidence collection when available; avoid destructive commands.
- Persist governance artifacts under `${CONFIG_ROOT}`-derived workspace paths, never inside the repo.

---

## Phase 1.4 — Addon Rules

Addon catalog: addons are discovered by scanning `${PROFILES_HOME}/addons/*.addon.yml`.
Manifest contract: `governance/assets/catalogs/PROFILE_ADDON_FACTORY_CONTRACT.json`.

Rules:
- `addon_class = required` — kernel blocks with `BLOCKED-MISSING-ADDON` if addon is missing.
- `addon_class = advisory` — kernel continues without blocking when addon is missing.
- Addons may be re-evaluated on re-entry to ensure deterministic activation.
- Addon activation and blocking semantics are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.

Merge behavior:
- Canonical conflict precedence is defined once in Section 1 (`PRIORITY ORDER`) and is not redefined here.
- Templates/addons refine generation and test structure but do not override master/core/profile constraints.
- Phase-4 re-entry performs delta evaluation and reloads only changed rulebooks/addons.

Output obligation: At Phase 4 entry, output includes a short activation summary.

---

## Data Sources

* Operational rules: `rules.md` (core technical rulebook) and the active profile rulebook (kernel-selected).
* Top-tier quality: `QUALITY_INDEX.md` (canonical index) and `CONFLICT_RESOLUTION.md` (priority model).

Preference rules:
1. Prefer existing repo conventions (frameworks, patterns, libs, naming, folder layout) if evidence-backed.
2. Prefer additive over breaking changes in any contract/schema surface.
3. Prefer minimal coherent change sets that keep diffs reviewable.
4. Prefer the narrowest safe scope (smallest component/module) when a repo is large.
5. If required evidence is missing for a gate decision, stop and request the minimal command output/artifact.

This governance system is single-user and does not require repo-working-tree-local governance or persistent artifacts.

---

## Phase 2 — Repo Discovery

Before repository discovery, if running under OpenCode (repository provided or indexed), check whether a persisted RepoMapDigest file exists and load it as context.
Repository evidence wins when contradictions occur; record as Risks.

Workspace memory is supportive defaults only; repository evidence always wins.

Fast Path: apply only when safety is provable (signature/head match).

---

## OpenAPI Codegen — Contract Validation Support

Purpose:
- Repo conventions win for style/tooling choices only if they do not weaken gates/evidence/scope lock.
- If a conflict cannot be resolved deterministically, record a risk and stop (BLOCKED) with a targeted question.

Rulebook load evidence: blocking behavior is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

---

## Phase 4 — Planning

0. **Phase-4 Entry:** Deterministic initialization; rulebook activation, workspace memory, required outputs are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

1. **Understand the requirement:**
   * Parse ticket description
   * Identify affected components (Phase 2 discovery), APIs (Phase 3 analysis), and business rules (Phase 1.5, if executed)
   * Cross-reference findings with the Codebase Context summary.

1a. **Classify Feature Complexity** (decision tree, binding):
    Classification fields, planning depth, and recording targets are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

2. **Produce Ticket Record (Mini-ADR + NFR Checklist):**
   **NFR checklist constraints:**
   - Cover at least: Security/Privacy, Observability, Performance, Migration/Compatibility, Rollback/Release safety.
   - Each item: `OK | N/A | Risk | Needs decision` + one sentence.

   **Architecture Options (A/B/C) constraints:**
   - Required whenever the plan involves any non-trivial decision surface.
   - At least Option A and Option B (Option C optional).
   - Each option: one-line description, key trade-offs (perf/complexity/operability/risk), test impact.
   - End with explicit Recommendation + confidence (0–100) + what evidence could change the decision.

3. **Create implementation plan:**
   * List all files to be created/modified
   * List all API changes (if contract changes)
   * Estimate complexity (simple, medium, complex)

4. **Identify risks:**
   * Breaking changes (API, database, etc.)
   - If evidence missing, output `MISSING_EVIDENCE: <id>` and stop.
   - The Risk Review is a format requirement, not an execution procedure.

**Phase 4 clarification scenarios:**
If CONFIDENCE LEVEL < 70% OR if multiple plausible implementations exist, ask for clarification.

**Phase 4 exit conditions:**
* Success: Plan created, CONFIDENCE >= 70% -> Proceed to Phase 5.

---

## Phase 5 — Review Gate

Code-producing output is NOT permitted during Phase 5.
Phase 5 is exclusively a review gate: architecture review, test-strategy review, and quality-gate evaluation.
Implementation (code, tests, configuration) begins only after all Phase 5 gates have passed and the session transitions to Phase 6.

**Rule A — Implementation-Intent Prohibition (Phase 5):**
Output classified as `implementation`, `patch`, `diff`, or `code_delivery` is forbidden during Phase 5.
This covers both code artifacts and implementation-intent language.
The canonical list of allowed and forbidden output classes is kernel-owned (see `${COMMANDS_HOME}/phase_api.yaml` under `output_policy` on token `"5"`).
All Phase 5 sub-tokens (5.3, 5.4, 5.5, 5.6) inherit this policy unless they define their own `output_policy` override.

**Rule B — Plan Self-Review Requirement (Phase 5):**
The first plan output in Phase 5 is a draft.
Before presenting any plan as review-ready, at least one internal self-review iteration is required.
The minimum number of self-review iterations is kernel-owned (see `${COMMANDS_HOME}/phase_api.yaml` under `output_policy.plan_discipline.min_self_review_iterations` on token `"5"`).

Phase 5/6 code-output constraints and gate sequencing are kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

**Actions:**

0. **Phase 5 gating and fast-path behavior:**
   Gate sequencing, fast-path scope, rollback safety evaluation, and scorecard requirements are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).
   Output class restrictions and plan self-review discipline are enforced by `output_policy` on token `"5"` in `phase_api.yaml`.

1. **Architectural review:**
   * Does the plan follow the repository's architecture pattern?
   * Are dependencies clean (no circular dependencies)?
   * Is the plan consistent with existing conventions?

1.5 **Ticket Record & NFR sanity check** (required):
    Ticket record/NFR checks, rollback safety, and state recording are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

2. **API contract review** (if API changes):
   Contract review rules and cross-repo impact recording are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

3. **Database schema review** (if schema changes):
   * Are migrations reversible (if possible)?
   * Are validations complete?
   * Are state transitions correct?

**Phase 5 gate results:**
* `architecture-approved`: Plan is sound, proceed to Phase 5.3.

### Phase 5.3 — Test Quality Review (CRITICAL Gate)

Phase 5.3 gate results:
* `test-quality-pass`: Tests are sufficient, proceed to Phase 6 (Implementation QA).

---

## Cognitive Complexity Check

* method: <= 15 (WARNING)
* nested levels: <= 3 (HIGH-RISK WARNING if >3)

---

## Phase 6 — Implementation QA

Binding prerequisites: gate prerequisites and readiness checks are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

Verification obligations: change-matrix updates and review-of-review checks are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

---

## Change Matrix

Every cross-cutting ticket requires a change matrix across planning/review.
Canonical matrix schema/template: `docs/governance/governance_schemas.md`.

---

## Response Rules

Response/output constraints are defined in `rules.md` and `governance/assets/schemas/*`.
`master.md` does not redefine response shape.

---

## Operator Commands

* "/explain-activation" (read-only activation report)

Override constraints:
- Skip-validation rules and blocked behavior are kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.
- Phase-skip restrictions are kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### Reload Contract

Reload routing, state updates, and continuation behavior are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

### Explain Contracts

Explain-command output shape and read-only guarantees are kernel-owned (`${COMMANDS_HOME}/phase_api.yaml`).

---

## Session Policies

### Clarification Format for Ambiguity

Canonical decision UX is kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

### BLOCKED — Recovery Playbook

Blocked output shape and recovery semantics are kernel-owned; see `governance/assets/reasons/blocked_reason_catalog.yaml`.

### Bootstrap Invocation Guard

Workflow does not ask operator to rerun the local bootstrap launcher in the same turn.

### Git Naming Contract

Commit/branch naming policy is tool- and workflow-owned.
See release/automation rules in `docs/releasing.md` and repo tooling (if present).

### Session Size Control

Session compression, preserved fields, and summary targets are kernel-owned; see `${COMMANDS_HOME}/phase_api.yaml`.

---
