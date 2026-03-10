# End-to-End Phases

This document is a detailed phase map that was previously embedded in README.md.
Authority boundary: policy, gate semantics, and routing are owned by kernel code plus kernel-owned configs/schemas; this file is explanatory and does not widen kernel behavior.

SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.
Kernel: `governance/kernel/*` is the only control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.

## Customer View (Short)

- Phase 0/1.1 performs bootstrap validation and preflight probes (including build tool detection). **Note:** Phase 0 is a customer-facing term; in the kernel, bootstrap logic is unified under Phase 1.1-Bootstrap.
- Phase 1.1 performs preflight and initializes the governance runtime.
- **Phase 1.2/1.3 are kernel-owned subphases** of the Rule Loading Pipeline (1.x family). They handle lazy rulebook loading and profile resolution and are routed by the kernel via `${COMMANDS_HOME}/phase_api.yaml`.
- Phase 1.5 is optional and acts as a bridge between discovery (2.1) and business rules.
- You may reference Phase 1.5 as 2.2 in customer-facing docs for alignment, but kernel semantics stay 1.5.
- 2.1 creates the Decision Pack; Phase 1.5 may run in parallel if signals exist, or follow 2.x for a stricter path.
- Bootstrap validates install/path/session prerequisites before work proceeds.
- Discovery builds repo context and reusable decision artifacts.
- Planning produces an implementation path without bypassing gates.
- Gate reviews validate architecture, tests, business rules (when enabled), and rollback safety.
- Final QA issues a deterministic readiness decision (ready-for-pr or fix-required).

## Full Phase Map

| Phase | What it does (one-line) | Gate / blocked behavior |
| ----- | ------------------------ | ----------------------- |
| Phase 0 - Bootstrap (conditional) | Validates variable/path bootstrap when required before workflow execution. | If bootstrap evidence or variable resolution is invalid/missing, workflow is `BLOCKED` (fail-closed). |
| Phase 1.1 - Preflight BuildToolchain | Probes ALL build-related tools on PATH (mvn, gradle, cargo, go, cmake, make, g++, dotnet, npm, etc.) and stores raw availability. | Non-gate phase; records tool availability for later Phase 2 resolution. |
| Phase 1 - Rules Loading | Loads rulebooks lazily in controlled order (bootstrap now, profile after discovery, core/templates/addons before planning). | Blocks if required rulebooks/evidence cannot be resolved for the current phase. |
| Phase 2 - Repository Discovery | Builds repo understanding (structure, stack, architecture signals, contract surface), with cache-assisted warm start when valid. | Non-gate phase, but missing required discovery artifacts can trigger `BLOCKED` continuation pointers. |
| Phase 2 Step 3a - CodebaseContext | Captures deep codebase understanding: ExistingAbstractions, DependencyGraph, PatternFingerprint, TechnicalDebtMarkers. | Non-gate phase; populates SESSION_STATE.CodebaseContext for informed planning. |
| Phase 2 Step 3b - BuildToolchain Resolution | Cross-references repo build files (pom.xml, Cargo.toml, go.mod, CMakeLists.txt, etc.) with preflight tool availability to resolve compile/test commands. | Non-gate phase; populates SESSION_STATE.BuildToolchain. Emits WARN-BUILD-TOOL-MISSING if tool unavailable. |
| Phase 2.1 - Routing Decision (no executor) | Routing checkpoint: if Phase 1.5 is unresolved, route to Phase 1.5; otherwise route to Phase 3A (or Phase 4 if API inventory is not applicable). | Decision point only; no phase executor runs here. |
| Phase 1.5 - Business Rules Discovery (optional) | Extracts business rules from code/ticket artifacts when activated or required. | Optional activation; once executed, Phase 5.4 becomes mandatory for code readiness. |
| Phase 3A - API Inventory | Inventories external API artifacts and interface landscape. | **Conditional**: Executed for all workflows, but if no APIs are in scope, records `not-applicable` and skips to Phase 4. Never blocks — missing APIs just mean no API validation needed. |
| Phase 3B-1 - API Logical Validation | Validates API specs for logical consistency at specification level. | **Conditional**: Only executed when Phase 3A detected APIs in scope. Skipped entirely if no APIs present. |
| Phase 3B-2 - Contract Validation (Spec <-> Code) | Validates contract fidelity between specification and implementation. | **Conditional**: Only executed when Phase 3A detected APIs in scope. Contract mismatches block readiness when contract gates are active/applicable. Skipped entirely if no APIs present. |
| Phase 4 - Ticket Execution (planning) | Produces the concrete implementation plan and review artifacts; no code output yet. | Planning phase; code-producing output remains blocked until explicit gate progression permits it. Supports a read-only rail entrypoint via `/review` for lead/staff depth feedback. |
| Phase 4 Step 1a - Feature Complexity Router | Classifies feature complexity (SIMPLE-CRUD, REFACTORING, MODIFICATION, COMPLEX, STANDARD) and determines planning depth. | Non-gate; determines which subsequent Phase 4 steps are required vs. optional. |
| Phase 5 - Lead Architect Review (gate) | Architecture gatekeeper review with explicit re-entry when changes are required. | Gate review; re-entry is explicit and required when issues remain. |
| Phase 5.3 - Test Quality Review (critical gate) | Reviews test strategy/coverage quality against gate criteria. | Critical gate; requires a passing outcome (or governed exceptions) before PR readiness. |
| Phase 5.4 - Business Rules Compliance (conditional gate) | Checks implemented plan/output against extracted business rules. | Mandatory only if Phase 1.5 ran; non-compliance blocks readiness. |
| Phase 5.5 - Technical Debt Proposal (optional gate) | Reviews and decides technical debt proposals and mitigation posture. | Optional gate; when activated, unresolved debt decisions can block approval. |
| Phase 5.6 - Rollback Safety | Evaluates rollback/recovery safety for relevant changes (within Phase 5 family). | Required when rollback-sensitive changes exist; failed rollback safety blocks progression. |
| Phase 6 - Implementation QA (final gate) | Final quality assurance and release-readiness decision (`ready-for-pr` vs `fix-required`). | Final explicit gate; failed QA blocks PR readiness. |
| Phase 6 - Build Verification Loop | Autonomous compile→fix→test→fix cycle when BuildToolchain is available (max 3 iterations each). | Non-gate phase; compiler output overrides self-critique when tools available. |

## Phase-Coupled Persistence (Outside Repository)

**SSOT Enforcement (Binding):** Persistence is mandatory and enforced by the kernel (not by LLM output).
The governance helpers (`bootstrap_session_state.py`, `persist_workspace_artifacts.py`) enable writes
when host permissions allow it in the current operating mode. In pipeline mode, interactivity is disabled; file writes follow host permissions and fail closed if not permitted.

| Phase | Artifact | Target | Write condition |
| ----- | -------- | ------ | --------------- |
| Phase 2 | `repo-cache.yaml` | `${REPO_CACHE_FILE}` (`[REPO-CACHE-FILE]`) | Written after successful discovery/cache refresh. |
| Phase 2 | `repo-map-digest.md` | `${REPO_DIGEST_FILE}` (`[REPO-MAP-DIGEST-FILE]`) | Written after successful digest generation. |
| Phase 2 | `workspace-memory.yaml` (observations/patterns) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Allowed for observational writeback when discovery evidence is sufficient. |
| Phase 2.1 | `decision-pack.md` | `${REPO_DECISION_PACK_FILE}` (`[DECISION-PACK-FILE]`) | Written when at least one decision/default is produced. |
| Phase 1.5+ | `business-rules.md` | `${REPO_BUSINESS_RULES_FILE}` (`[BR-INVENTORY-FILE]`) | Written only when BusinessRules outcome is `extracted` with extractor evidence; otherwise status is tracked in `business-rules-status.md`. |
| Phase 5 (conditional) | `workspace-memory.yaml` (decisions/defaults) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Only when Phase 5 is approved and user confirms exactly: `Persist to workspace memory: YES`. |

## Canonical Flow

```
0 -> 1.1 (Preflight) -> 1 -> 2 -> 2.1
After 2.1: resolve Phase 1.5 decision (explicit request/explicit skip/A-B decision).
Once 1.5 is resolved: if APIs are in scope, run 3A -> 3B-1 -> 3B-2; otherwise go to 4.
Main execution path: 4 -> 5 -> 5.3 -> 6.
5.4 is mandatory only if 1.5 executed.   (5.3 -> 5.4 -> ... -> 6)
5.5 is always checked but may be not-applicable.  (5.3/5.4 -> 5.5 -> ... -> 6)
5.6 is required when rollback safety applies.  (5.3/5.4/5.5 -> 5.6 -> 6)
Phase 6 internal: Implementation Internal Review (max 3 iterations)
  -> Evidence Presentation Gate -> /review-decision (approve|changes_requested|reject).
```

## Phase 3 Routing (API Detection)

Phase 3 is **conditionally executed** based on API presence:

| Condition | Phase 3A | Phase 3B-1/3B-2 | Flow |
|-----------|----------|------------------|------|
| External API artifacts provided | Executed | Executed | 3A → 3B-1 → 3B-2 → 4 |
| Repo contains OpenAPI/GraphQL specs | Executed | Executed | 3A → 3B-1 → 3B-2 → 4 |
| No APIs in scope | Executed (not-applicable) | Skipped | 3A → 4 directly |

**Key insight:** Phase 3A is executed by default but may immediately exit with `not-applicable` status. Phase 3B-1 and 3B-2 are only executed when APIs are actually present.

**Implementation note:** Phase routing is kernel-enforced by `governance/kernel/*` against `${COMMANDS_HOME}/phase_api.yaml`. The routing includes:
- Phase 2.1 → Phase 1.5 (Business Rules Discovery decision)
- Phase 1.5 → Phase 3A (default routing; kernel-enforced)
- Phase 2.1 → Phase 3A (default routing; 3A may exit with not-applicable; kernel-enforced)
- Phase 3A → Phase 3B-1 (if APIs in scope) OR Phase 4 (if no APIs, not-applicable)
- Phase 3B-1 → Phase 3B-2 (contract validation)
- Phase 3B-2 → Phase 4

## Phase 5 Review Gate

Phase 5 is an explicit gate with **manual re-entry** when changes are required. It does not enforce a fixed number of automatic review rounds; re-entry is triggered by the operator when a revised plan is ready.

### Review Cycle (explicit re-entry)

```
Phase 4 (Plan) → Phase 5 Review
                       ↓
                Feedback: Issues / Suggestions / Questions
                       ↓
              Issues remain? → return to Phase 4 (revise plan)
                       ↓
              Operator re-enters Phase 5 for another review
```

### Implementation Notes

Phase 5 review state may be tracked in `SESSION_STATE.Gates.*` and any optional review metadata. The authoritative gate conditions remain:

- `Gates.P5-Architecture = architecture-approved`
- `Gates.P5.3-TestQuality = pass|pass-with-exceptions`
- `Gates.P5.4-BusinessRules = compliant|compliant-with-exceptions` (only if Phase 1.5 executed)
- `Gates.P5.5-TechnicalDebt = approved|not-applicable` (always checked)
- `Gates.P5.6-RollbackSafety = approved|not-applicable` (when rollback safety applies)

## Phase 6 Review Decision

Phase 6 contains an internal loop and a final review decision mechanism:

### Implementation Internal Review (autonomous)

```
Phase 6 entry (prerequisites validated)
  -> Implementation Internal Review (up to 3 iterations)
     - Each iteration compares prev_impl_digest vs curr_impl_digest
     - Early-stop when digest is unchanged (no revision delta)
     - Hard-stop when max iterations reached
  -> Evidence Presentation Gate (review complete)
```

### Review Decision (operator-driven)

At the Evidence Presentation Gate, the operator must run `/review-decision` with one of:

| Decision | Effect |
|----------|--------|
| `approve` | Workflow Complete — terminal state within Phase 6 (`workflow_complete=true`) |
| `changes_requested` | Enter `Rework Clarification Gate` in Phase 6 — clarify in chat first, then run exactly one directed rail (`/ticket`, `/plan`, or `/continue`) |
| `reject` | Back to Phase 4 — restart from planning (Ticket Input Gate) |

**Key:** `/continue` does NOT advance past the Evidence Presentation Gate. The operator must explicitly run `/review-decision`.

## Gate Requirements for Code Generation

Phase 3 API validation is **optional** and does NOT block code generation. The gates required before code output:

| Gate | Phase | Required? | Condition |
|------|-------|-----------|-----------|
| P5-Architecture | 5 | Unconditional | Requires `approved` status (after iterative review) |
| P5.3-TestQuality | 5.3 | Unconditional | Requires `pass` or `pass-with-exceptions` |
| P5.4-BusinessRules | 5.4 | Conditional | Only if Phase 1.5 was executed |
| P5.5-TechnicalDebt | 5.5 | Unconditional | Always checked; `approved` or `not-applicable` required |
| P5.6-RollbackSafety | 5.6 | Conditional | When rollback-sensitive changes exist |
| P6-ImplementationQA | 6 | Unconditional | Requires `ready-for-pr` |

## Phase 4 Intake Contract

- Inputs may come from chat text or a ticket file path, but both must use the same local intake writer.
- Phase progression is unlocked only by persisted intake evidence (`Ticket`/`Task` with matching digest fields).
- `phase4_intake_evidence=true` is supporting metadata and never sufficient by itself.
- `/ticket` is the mutating intake rail for Phase 4 evidence persistence.
- `/plan` is the mutating plan-record rail for Phase 5 evidence persistence.
- `/continue` and `/review` remain read-only rails and do not mutate intake/plan evidence.
- `FeatureComplexity` can be persisted as supporting metadata but does not unlock Phase 4 on its own.

## Key SESSION_STATE Fields by Phase

| Phase | Key SESSION_STATE Additions |
| ----- | --------------------------- |
| Phase 1.1 | `Preflight.BuildToolchain.DetectedTools`, `ObservedAt` |
| Phase 2 | `RepoMapDigest`, `DecisionDrivers`, `WorkingSet`, `TouchedSurface` |
| Phase 2 Step 3a | `CodebaseContext` (ExistingAbstractions, DependencyGraph, PatternFingerprint, TechnicalDebtMarkers) |
| Phase 2 Step 3b | `BuildToolchain` (CompileAvailable, CompileCmd, TestAvailable, TestCmd, FullVerifyCmd, BuildSystem, MissingTool) |
| Phase 4 Step 1a | `FeatureComplexity` (Class, Reason, PlanningDepth) |
| Phase 5 | `Gates.P5-Architecture`, `Phase5Review` (Iteration, PlanVersion, Status, FeedbackHistory), `Gates.P5.3-TestQuality`, `Gates.P5.4-BusinessRules`, `Gates.P5.5-TechnicalDebt`, `Gates.P5.6-RollbackSafety` |
| Phase 6 | `Gates.P6-ImplementationQA`, `BuildEvidence` (status, CompileResult, TestResult, IterationsUsed, ToolOutput) |
