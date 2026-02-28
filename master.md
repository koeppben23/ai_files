- Deterministic activation summary: `RepoFacts -> Capabilities -> Packs/Profile -> activation_hash/ruleset_hash -> Gate`.
- This file is operator guidance and should avoid duplicating low-level algorithmic details that are contract-tested in code.

Authority boundary: Schemas, validators, and kernel code are authoritative. This Markdown is not SSOT and does not define runtime truth. It provides operator guidance only and must reference authoritative sources for any behavior, format, or state. When in doubt, follow the schema/validator/kernel reference.

SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.
- Schema IDs are versioned (`schema: governance.<area>.<name>.v1`).
- Compact presentation schema is optional: `governance.compact_mode.v1`.

Doc-lint standard: `docs/governance/doc_lint.md`.

## Authority Index (Rail-only Guidance - See rulesets/core/rules.yml for authoritative data)

Authoritative sources by area (see rulesets/core/rules.yml for machine-readable authoritative data):
- Routing/validation/transitions: `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*`
- Session-state shape and invariants: `SESSION_STATE_SCHEMA.md` and `governance/assets/schemas/*`
- Response envelope and presentation shape: `governance/RESPONSE_ENVELOPE_SCHEMA.json`
- Blocked reason catalog: `governance/assets/reasons/blocked_reason_catalog.yaml`
- Bootstrap gating policy: `governance/assets/config/bootstrap_policy.yaml`
- Path validation rules: `governance/engine/session_state_invariants.py`


## PHASE 0 — BOOTSTRAP (CONDITIONAL)


> **BLOCKED — Bootstrap not satisfied**

Terminology (docs-owned explanatory):
- **Plan-Gates** are explicit decision gates that control whether code-producing output is described.
- **Evidence-Gates** are evidence prerequisites required to claim a gate outcome; a Plan-Gate may be
  logically satisfied but still **blocked** if evidence is missing.

When blocked, kernel-owned state and reason codes apply.
See `governance/assets/reasons/blocked_reason_catalog.yaml` for authoritative blocked reasons.

### Recovery
- Operator must restate the bootstrap declaration explicitly.

## GLOBAL PATH VARIABLES (Rail-only Guidance)

Path variables, resolution rules, and persistence topology are kernel- and schema-owned.
This markdown section is a rail-only summary for operators.

Authoritative sources:
- Path and persistence schema: `SESSION_STATE_SCHEMA.md` and `governance/assets/schemas/*`
- Path invariants and validation: `governance/engine/session_state_invariants.py`
- Blocked reason catalog: `governance/assets/reasons/blocked_reason_catalog.yaml`

Operator guidance (docs-owned explanatory):
- Always express paths using canonical variables in outputs.
- Treat absolute host paths as evidence-only, not canonical.

Command inventory, preflight, identity evidence collection, and persistence targets are kernel- and schema-owned.
Authoritative sources:
- Command inventory and tooling policy: `governance/assets/catalogs/tool_requirements.json`
- Preflight schema: `docs/governance/governance_schemas.md` (`governance.preflight.v1`)
- Path invariants and persistence rules: `governance/engine/session_state_invariants.py`
- Session-state schema: `SESSION_STATE_SCHEMA.md`
Operator guidance (docs-owned explanatory):
- Prefer host-side evidence collection when available; avoid destructive commands.
- Persist governance artifacts under `${CONFIG_ROOT}`-derived workspace paths, never inside the repo.

consolidated, model-stable, hybrid-capable, pragmatic,
with architecture, contract, debt & QA gates
  - QUALITY_INDEX.md
  - CONFLICT_RESOLUTION.md

Bootstrap session-state shape is schema-owned.
See `SESSION_STATE_SCHEMA.md` and `governance/assets/schemas/session_state.core.v1.schema.json`.
  
### Phase 1.2: Profile Detection

> **Routing:** Kernel-enforced from `${COMMANDS_HOME}/phase_api.yaml`.

Profile selection is kernel-enforced.
Auto-selection may persist profile choice and evidence in session state; see `SESSION_STATE_SCHEMA.md`.

### Phase 1.3: Core Rules Activation

> **Routing:** Kernel-enforced from `${COMMANDS_HOME}/phase_api.yaml`.

Core rulebook activation outputs are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

#### Execution Constraints (Kernel-Owned)

Phase constraints are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`.


### Phase 1.4: Templates & Addons Activation
Activation Steps (Informational):

> **Note:** Activation preconditions and failure handling are kernel-enforced.
> See `governance/assets/reasons/blocked_reason_catalog.yaml` for authoritative reasons.

Activation steps and session-state mutations are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

   Addon catalog (informational):
   - Addons are discovered dynamically by scanning addon manifests located at:
   - `${PROFILES_HOME}/addons/*.addon.yml`
   - Manifest contract is schema-owned. See `governance/assets/catalogs/PROFILE_ADDON_FACTORY_CONTRACT.json`.

   Rules (informational):
   - Manifest field `addon_class` (`required` | `advisory`) declares addon enforcement mode.
   - `addon_class = required` -> kernel blocks with `BLOCKED-MISSING-ADDON` if addon is missing.
   - `addon_class = advisory` -> kernel continues without blocking when addon is missing.
   - Addons may be re-evaluated on re-entry to ensure deterministic activation.
   - Addon activation and blocking semantics are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.

   Kafka addon example: see addon manifest and rulebook for details.

4) Merge behavior (non-precedence)
   - Canonical conflict precedence is defined once in Section 1 (`PRIORITY ORDER`) and MUST NOT be redefined here.
   - Templates/addons MUST be followed when loaded; they refine generation and test structure but MUST NOT override master/core/profile constraints.
   - Re-entry optimization: Phase-4 re-entry MUST perform delta evaluation (what changed since last activation)
     and reload only changed rulebooks/addons.
    - Activation delta determinism is kernel-owned. See `governance/kernel/*` and session-state schema.

Output obligation (BINDING):
- At Phase 4 entry, output includes a short activation summary (schema-owned).
 
### Data sources (non-precedence)

* Operational rules (technical, architectural) are defined in:
  - `rules.md` (core technical rulebook)
  - the active profile rulebook (kernel-selected; see `${COMMANDS_HOME}/phase_api.yaml`)
* Top-tier quality definition and deterministic conflict handling are defined in:
  - `QUALITY_INDEX.md` (canonical top-tier index; no new rules)
  - `CONFLICT_RESOLUTION.md` (priority model for contradictions)
- `workspace repo bucket` = `${REPO_HOME}` under `${WORKSPACES_HOME}/<repo_fingerprint>` (outside repo working tree).

This governance system is single-user and MUST NOT require repo-working-tree-local governance or persistent artifacts.
Persistence and rulebook loading are kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

#### Step 1 (Phase 1.3): Resolve Core Rulebook (rules.md)

Lookup paths are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

#### Step 1b (Phase 1.1): Resolve Top-Tier Index & Conflict Model (QUALITY_INDEX.md, CONFLICT_RESOLUTION.md)

These files are required in the same governance installation scope as `master.md`.

Missing top-tier files behavior is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml` and blocked reason catalog.

Top-tier load evidence obligation is schema-owned. See `SESSION_STATE_SCHEMA.md`.

Reference lookup paths are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.
3. Context: manually provided (planning-only)

#### Step 2: Load Profile Rulebook (AUTO-DETECTION ADDED)

Profile selection is kernel-enforced.
Auto-selection may persist profile choice and evidence in session state; see `SESSION_STATE_SCHEMA.md`.

---

## OPENAPI CODEGEN (GENERATED DTOs) — CONTRACT VALIDATION SUPPORT (BINDING)

OpenAPI codegen scanning rules are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

### PURPOSE

2) **Repo conventions win** for style/tooling choices **only if** they do not weaken gates/evidence/scope lock.
3) If the conflict still cannot be resolved deterministically, record a risk and stop (BLOCKED) with a targeted question.

Addon/template conflict handling is kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/assets/reasons/blocked_reason_catalog.yaml`.

### Rulebook Load Evidence (BINDING)

Rulebook load evidence rules and blocking behavior are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `governance/assets/reasons/blocked_reason_catalog.yaml`.

---

- `5.6` is evaluated inside `5` and applies when rollback safety is relevant.

**Output Rule for Code Generation:**
Code-generation gating is kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

Additionally, any mandatory gates defined in `rules.md` (e.g., Contract & Schema Evolution Gate, Change Matrix Verification)
MUST be explicitly passed when applicable.
P5.3 is a CRITICAL quality gate that must be satisfied before concluding readiness for PR (P6),
but it does not forbid drafting/iterating on tests and implementation during Phase 5.
Clarification:
- Phase 5/6 code-output constraints and gate sequencing are kernel- and schema-owned.
  See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.
 
---

* "/explain-activation" (read-only activation report) → execute explain contract in Section 2.2.2

Override constraints (Rail-only Guidance):
Skip-validation rules and blocked behavior are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`.

Phase-skip restrictions are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`.

### 2.2.1 Operator Reload Contract (Kernel-Enforced)

Reload routing, state updates, and continuation behavior are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

### 2.2.2 Operator Explain Contracts (Binding, read-only)

Explain-command output shape and read-only guarantees are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

---


#### Clarification Format for Ambiguity (Policy)

Clarification format is rail-only guidance. Canonical decision UX is kernel-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

#### Confidence bands for Auto-Advance (Policy)

Confidence thresholds and auto-advance rules are kernel-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

#### BLOCKED — Recovery Playbook (Output Format)

Blocked output shape and recovery semantics are schema- and kernel-owned.
See `governance/RESPONSE_ENVELOPE_SCHEMA.json` and `governance/assets/reasons/blocked_reason_catalog.yaml`.

#### Unified Next Action Footer (Presentation Advisory)

Presentation conventions are rail-only. See `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

#### Confidence + Impact Snapshot (Presentation Advisory)

Snapshot fields are schema-owned. See `SESSION_STATE_SCHEMA.md` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

#### Definition: Explicit gates (Auto-Advance stops)

Explicit gate behavior, outputs, and operator prompts are kernel- and schema-owned.
See `governance.phase5.gates.v1`, `governance.phase6.qa.v1`, and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

---


### 2.4.1 Session Start Mode Banner (Kernel-Enforced)

Session start banner format and evidence requirements are kernel-owned.
See `governance/RESPONSE_ENVELOPE_SCHEMA.json` and `SESSION_STATE_SCHEMA.md`.

### 2.4.2 Architect-Only Autopilot Lifecycle (Policy)

bootstrap invocation guard (Rail-only Guidance):
- Workflow MUST NOT ask operator to rerun the local bootstrap launcher in the same turn.

Execution mode enum and blocked reasons are schema- and kernel-owned.
See `SESSION_STATE_SCHEMA.md` and `governance/assets/reasons/blocked_reason_catalog.yaml`.

Detailed lifecycle routing and mode transition behavior is maintained outside `master.md`:
- Kernel/config contracts for binding behavior
1) **Prefer existing repo conventions** (frameworks, patterns, libs, naming, folder layout) if evidence-backed.
2) **Prefer additive over breaking changes** in any contract/schema surface.
3) **Prefer minimal coherent change sets** that keep diffs reviewable.
4) **Prefer the narrowest safe scope** (smallest component/module) when a repo is large; scope recording is kernel- and schema-owned.
5) If required evidence is missing for a gate decision, stop and request the minimal command output/artifact (no speculative gate passes).

Auto-advance continues until:

### 2.6 Conventional Git Naming Contract (Binding when Git operations are requested)

Commit/branch naming policy is tool- and workflow-owned.
See release/automation rules in `docs/releasing.md` and repo tooling (if present).

---

## 3. SESSION STATE (REQUIRED)

Session-state shape, output modes, and required fields are schema- and kernel-owned.
See `SESSION_STATE_SCHEMA.md`, `governance/assets/schemas/session_state.core.v1.schema.json`, and `${COMMANDS_HOME}/phase_api.yaml`.

---

## 4. PHASE 1 TOKEN OUTPUT (BINDING)

Phase tokenization and `SESSION_STATE.Next` semantics are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

---


If contradictions occur, repository evidence ALWAYS wins and MUST be recorded as Risks.

Repo cache handling is kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md` and `${COMMANDS_HOME}/phase_api.yaml`.

Before performing repository discovery, if the workflow is running under OpenCode
(repository provided or indexed via OpenCode), the workflow MUST check whether a
persisted RepoMapDigest file exists and load it as context.

RepoMapDigest handling is kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md` and `${COMMANDS_HOME}/phase_api.yaml`.

#### Load Existing Workspace Memory (Kernel-Managed, Read-Before-Use)

- Stabilize repo-specific conventions and reduce drift across ticket sessions.
- Workspace Memory is supportive defaults only; repository evidence always wins.

Workspace memory handling is kernel- and schema-owned. See `SESSION_STATE_SCHEMA.md` and `${COMMANDS_HOME}/phase_api.yaml`.

#### Fast Path (Optional, Conservative)

- Reduce repeated discovery across ticket sessions.
- Apply ONLY when safety is provable (signature/head match).

Fast Path eligibility and repo signature computation are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

Phase 2 discovery actions and Codebase Context are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

3b. **Resolve Build Toolchain (Kernel-Enforced):**

Build-toolchain resolution and any `SESSION_STATE.BuildToolchain` fields are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md` for authoritative behavior.

4. **Verify against profile:**

Profile mismatch handling is kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

#### Phase-Coupled Persistence Gate (Mandatory)

Persistence gates and file outputs are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

RepoMapDigest persistence and workspace memory format are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

Phase 2.1 (Decision Pack) is kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

#### Load Existing Decision Pack (Kernel-Managed, Read-Before-Write)

Decision pack format, lifecycle, and session-state updates are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

#### Persist Decision Pack (Kernel-Enforced, Mandatory After Phase 2.1)

Decision pack persistence is kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

Phase 2 exit conditions are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

---

### PHASE 1.5 — Business Rules Discovery (Conditional)

Execution timing and re-entry rules are kernel-owned. See `${COMMANDS_HOME}/phase_api.yaml`.

#### Business Rules Inventory (Kernel-Enforced)

Business rules extraction, inventory format, persistence, and exit conditions are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `governance/assets/config/persistence_artifacts.yaml`.

---

### PHASE 3A — API Inventory (External Artifacts)

API inventory inputs, outputs, and transitions are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

### PHASE 3B-1 — API Logical Validation (Spec-Level)

Spec validation rules, blocked conditions, and output shape are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

### PHASE 3B-2 — Contract Validation (Spec ↔ Code)

Contract validation rules, non-blocking conditions, and output shape are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

---



0. **Phase-4 Entry: Deterministic initialization (BINDING)**
   - Phase-4 entry sequencing, rulebook activation, workspace memory handling, and required outputs are kernel- and schema-owned.
   - See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

1. **Understand the requirement:**
   * Parse ticket description
   * Identify affected components (based on Phase 2 discovery)
   * Identify affected APIs (based on Phase 3 analysis)
   * Identify affected business rules (based on Phase 1.5, if executed)
   * Cross-reference findings with the Codebase Context summary (kernel-owned).

1a. **Classify Feature Complexity (Decision Tree — Binding):**

   |      Test strategy: Profile-prescribed test pyramid.
   ```

   Classification fields, planning depth implications, and recording targets are kernel- and schema-owned.
   See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

2. **Produce Ticket Record (Mini-ADR + NFR Checklist) — REQUIRED:**
   The goal is to reduce user cognitive load and make the ticket’s key trade-offs explicit.
   **NFR checklist constraints (Rail-only Guidance):**
   - Cover at least: Security/Privacy, Observability, Performance, Migration/Compatibility, Rollback/Release safety.
   - Each item must be one short line: `OK | N/A | Risk | Needs decision` + one sentence.
    - If anything is `Risk` or `Needs decision`, record it via kernel- and schema-owned risk/blocker fields.

   **Architecture Options (A/B/C) constraints (Rail-only Guidance):**
   - REQUIRED whenever the plan involves any non-trivial decision surface (examples: boundaries, persistence approach,
   - MUST list at least **Option A** and **Option B** (Option C optional).
   - Each option MUST include: one-line description, key trade-offs (perf/complexity/operability/risk), and test impact.
   - MUST end with an explicit **Recommendation** (one option) + confidence (0–100) + what evidence could change the decision.
    - The final choice recording is kernel- and schema-owned.

3. **Create implementation plan:**
   * List all files to be created/modified
   * List all API changes (if contract changes)
   * Estimate complexity (simple, medium, complex)

    **Test strategy constraints (Rail-only Guidance):**
    Test strategy requirements and format are kernel- and schema-owned.
    See `${COMMANDS_HOME}/phase_api.yaml` and `docs/governance/governance_schemas.md`.

   **Mandatory Review Matrix constraints (Rail-only Guidance):**
   - The MRM is kernel- and schema-owned. See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

   Touched-surface tracking and Fast Path evaluation are kernel- and schema-owned.
   See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

4. **Identify risks:**
   * Breaking changes (API, database, etc.)
   - If evidence missing, output `MISSING_EVIDENCE: <id>` and stop
   - The Risk Review is a format requirement, not an execution procedure

   Self-review evidence, iteration behavior, and any build-toolchain awareness are kernel- and schema-owned.
   See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

 **Output format (schema: governance.phase4.plan.v1):**

See `docs/governance/governance_schemas.md` and the schema registry for the authoritative plan output shape.

 **Phase 4 clarification scenarios:**

If CONFIDENCE LEVEL < 70% OR if multiple plausible implementations exist, the workflow may ask for clarification using the mandatory format (Section 2.3).

Example clarification format is kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

**Phase 4 exit conditions:**
* Success: Plan created, CONFIDENCE ≥ 70% → Proceed to Phase 5

### Session size control (long sessions)

Session compression, preserved fields, and summary targets are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

### PHASE 5 — Lead Architect Review (Gatekeeper)


**Actions:**

 0. **Phase 5 gating and fast-path behavior (Kernel-Enforced):**
    Gate sequencing, fast-path scope, rollback safety evaluation, and scorecard requirements are kernel- and schema-owned.
    See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

1. **Architectural review:**
   * Does the plan follow the repository's architecture pattern?
   * Are dependencies clean (no circular dependencies)?
   * Is the plan consistent with existing conventions?
   
 1.5 **Ticket Record & NFR sanity check (REQUIRED):**
   Ticket record/NFR checks, rollback safety expectations, and associated state recording are kernel- and schema-owned.
   See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

 2. **API contract review (if API changes):**
    Contract review rules and cross-repo impact recording are kernel- and schema-owned.
    See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

3. **Database schema review (if schema changes):**
   * Are migrations reversible (if possible)?
   * Are validations complete?
   * Are state transitions correct?

  **Output format (schema: governance.phase5.gates.v1):**

See `docs/governance/governance_schemas.md` and `governance/RESPONSE_ENVELOPE_SCHEMA.json` for the authoritative gate output shape.

**Phase 5 gate results:**
* `architecture-approved`: Plan is sound, proceed to Phase 5.3

#### Workspace Memory writeback (Decisions/Defaults) — Binding

Workspace memory writeback eligibility, format, and state updates are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

### PHASE 5.3 — Test Quality Review (CRITICAL Gate)


 **Output format (schema: governance.phase5.gates.v1):**

See `docs/governance/governance_schemas.md` and `governance/RESPONSE_ENVELOPE_SCHEMA.json` for the authoritative gate output shape.

**Phase 5.3 gate results:**
* `test-quality-pass`: Tests are sufficient, proceed

### PHASE 5.4 — Business Rules Compliance (only if Phase 1.5 executed)

Business rules compliance checks, gap handling, and output format are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

---


**Output:**

Domain model quality reporting is kernel- and schema-owned.
See `docs/governance/governance_schemas.md`.

### Code Complexity Checks (Phase 5.7 — internal check)

}
```

Refactoring hints and complexity warning formats are kernel- and schema-owned.
See `docs/governance/governance_schemas.md`.

### Cognitive Complexity Check

* method: ≤ 15 (WARNING)
* nested levels: ≤ 3 (HIGH-RISK WARNING if >3)

Complexity report output shape is kernel- and schema-owned.
See `docs/governance/governance_schemas.md`.

---

### PHASE 6 — Implementation QA (Self-Review Gate)

**Binding prerequisites:**
Gate prerequisites and readiness checks are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml` and `SESSION_STATE_SCHEMA.md`.

**Verification obligations (Rail-only Guidance):**
Verification obligations, change-matrix updates, and review-of-review checks are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `governance/RESPONSE_ENVELOPE_SCHEMA.json`.

#### Build Verification Output Contract (Presentation Advisory, schema: governance.phase6.qa.v1)

Build verification commands, evidence fields, and output requirements are kernel- and schema-owned.
See `${COMMANDS_HOME}/phase_api.yaml`, `SESSION_STATE_SCHEMA.md`, and `docs/governance/governance_schemas.md`.

---

## 5. CHANGE MATRIX (Kernel-Enforced)

Every cross-cutting ticket requires a change matrix across planning/review.
Canonical matrix schema/template is external. See `docs/governance/governance_schemas.md`.

---

## 6. RESPONSE RULES

Response/output constraints are defined in `rules.md` and authoritative schemas.
`master.md` does not redefine response shape.

---

