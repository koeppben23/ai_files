# End-to-End Phases

This document is the detailed phase map that was previously embedded in README.md. If this file and master.md diverge, master.md is authoritative.
Kernel authority boundary: policy and gate semantics are owned by kernel contracts (`master.md` + engine/use-case enforcement); this file is explanatory and must never widen kernel behavior.

## Customer View (Short)

- Phase 0/1.1 performs bootstrap validation and preflight probes (including build tool detection). **Note:** Phase 0 is a customer-facing term; in the kernel, bootstrap logic is unified under Phase 1.1-Bootstrap.
- Phase 1.1 performs preflight and initializes the governance runtime.
- **Phase 1.2/1.3 are kernel-internal subphases** of the Rule Loading Pipeline (1.x family) and are not exposed as routable phases. They handle lazy rulebook loading and profile resolution.
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
| Phase 2.1 - Decision Pack (default, non-gate) | Distills discovery outputs into reusable decisions/defaults for later phases. | Non-gate; if evidence is insufficient, decisions remain `not-verified` and downstream confidence is capped. |
| Phase 1.5 - Business Rules Discovery (optional) | Extracts business rules from code/ticket artifacts when activated or required. | Optional activation; once executed, Phase 5.4 becomes mandatory for code readiness. |
| Phase 3A - API Inventory | Inventories external API artifacts and interface landscape. | **Conditional**: Executed for all workflows, but if no APIs are in scope, records `not-applicable` and skips to Phase 4. Never blocks — missing APIs just mean no API validation needed. |
| Phase 3B-1 - API Logical Validation | Validates API specs for logical consistency at specification level. | **Conditional**: Only executed when Phase 3A detected APIs in scope. Skipped entirely if no APIs present. |
| Phase 3B-2 - Contract Validation (Spec <-> Code) | Validates contract fidelity between specification and implementation. | **Conditional**: Only executed when Phase 3A detected APIs in scope. Contract mismatches block readiness when contract gates are active/applicable. Skipped entirely if no APIs present. |
| Phase 4 - Ticket Execution (planning) | Produces the concrete implementation plan and review artifacts; no code output yet. | Planning phase; code-producing output remains blocked until explicit gate progression permits it. |
| Phase 4 Step 1a - Feature Complexity Router | Classifies feature complexity (SIMPLE-CRUD, REFACTORING, MODIFICATION, COMPLEX, STANDARD) and determines planning depth. | Non-gate; determines which subsequent Phase 4 steps are required vs. optional. |
| Phase 5 - Lead Architect Review (iterative gate) | Architecture gatekeeper review with up to 3 review iterations. Each iteration produces structured feedback (issues, suggestions, questions). | Iterative gate; approved after issues resolved OR escalated to human after max 3 iterations. |
| Phase 5.3 - Test Quality Review (critical gate) | Reviews test strategy/coverage quality against gate criteria. | Critical gate; must pass (or pass with governed exceptions) before PR readiness. |
| Phase 5.4 - Business Rules Compliance (conditional gate) | Checks implemented plan/output against extracted business rules. | Mandatory only if Phase 1.5 ran; non-compliance blocks readiness. |
| Phase 5.5 - Technical Debt Proposal (optional gate) | Reviews and decides technical debt proposals and mitigation posture. | Optional gate; when activated, unresolved debt decisions can block approval. |
| Phase 5.6 - Rollback Safety | Evaluates rollback/recovery safety for relevant changes (within Phase 5 family). | Required when rollback-sensitive changes exist; failed rollback safety blocks progression. |
| Phase 6 - Implementation QA (final gate) | Final quality assurance and release-readiness decision (`ready-for-pr` vs `fix-required`). | Final explicit gate; failed QA blocks PR readiness. |
| Phase 6 - Build Verification Loop | Autonomous compile→fix→test→fix cycle when BuildToolchain is available (max 3 iterations each). | Non-gate phase; compiler output overrides self-critique when tools available. |

## Phase-Coupled Persistence (Outside Repository)

**Kernel Enforcement (Binding):** Persistence is MANDATORY and MUST be enforced by the kernel, not by LLM output.
The diagnostics helpers (`bootstrap_session_state.py`, `persist_workspace_artifacts.py`) MUST enable writes
when `OPENCODE_DIAGNOSTICS_ALLOW_WRITE=1` is set (default in normal operation). In CI mode, writes are
disabled for safety.

| Phase | Artifact | Target | Write condition |
| ----- | -------- | ------ | --------------- |
| Phase 2 | `repo-cache.yaml` | `${REPO_CACHE_FILE}` (`[REPO-CACHE-FILE]`) | Written after successful discovery/cache refresh. |
| Phase 2 | `repo-map-digest.md` | `${REPO_DIGEST_FILE}` (`[REPO-MAP-DIGEST-FILE]`) | Written after successful digest generation. |
| Phase 2 | `workspace-memory.yaml` (observations/patterns) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Allowed for observational writeback when discovery evidence is sufficient. |
| Phase 2.1 | `decision-pack.md` | `${REPO_DECISION_PACK_FILE}` (`[DECISION-PACK-FILE]`) | Written when at least one decision/default is produced. |
| Phase 1.5 | `business-rules.md` | `${REPO_BUSINESS_RULES_FILE}` (`[BR-INVENTORY-FILE]`) | Written when Business Rules Discovery is executed. |
| Phase 5 (conditional) | `workspace-memory.yaml` (decisions/defaults) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Only when Phase 5 is approved and user confirms exactly: `Persist to workspace memory: YES`. |

## Canonical Flow

```
0 -> 1.1 (Preflight) -> 1 -> 2 -> 2.1
After 2.1: resolve Phase 1.5 decision (explicit request/explicit skip/A-B decision).
Once 1.5 is resolved: if APIs are in scope, run 3A -> 3B-1 -> 3B-2; otherwise go to 4.
Main execution path: 4 -> 5 -> 5.3 -> 6.
5.4 is mandatory only if 1.5 executed.
5.5 is optional and only when explicitly proposed.
5.6 is evaluated inside 5 and MUST be satisfied when rollback safety applies.
```

## Phase 3 Routing (API Detection)

Phase 3 is **conditionally executed** based on API presence:

| Condition | Phase 3A | Phase 3B-1/3B-2 | Flow |
|-----------|----------|------------------|------|
| External API artifacts provided | Executed | Executed | 3A → 3B-1 → 3B-2 → 4 |
| Repo contains OpenAPI/GraphQL specs | Executed | Executed | 3A → 3B-1 → 3B-2 → 4 |
| No APIs in scope | Executed (not-applicable) | Skipped | 3A → 4 directly |

**Key insight:** Phase 3A is always executed but may immediately exit with `not-applicable` status. Phase 3B-1 and 3B-2 are only executed when APIs are actually present.

**Implementation note:** Phase routing is implemented in `phase_router.py`. The routing includes:
- Phase 2.1 → Phase 1.5 (Business Rules Discovery decision)
- Phase 1.5 → Phase 3A (always, per docs requirement)
- Phase 2.1 → Phase 3A (always, per docs requirement - 3A may exit with not-applicable)
- Phase 3A → Phase 3B-1 (if APIs in scope) OR Phase 4 (if no APIs, not-applicable)
- Phase 3B-1 → Phase 3B-2 (contract validation)
- Phase 3B-2 → Phase 4

## Phase 5 Iterative Review

Phase 5 uses an **iterative review mechanism** to improve plan quality:

### Review Cycle

```
Phase 4 (Plan v1) → Phase 5 Review Round 1
                           ↓
                    Feedback: Issues[], Suggestions[], Questions[]
                           ↓
                   Issues exist? → Phase 4 (Plan v2) → Review Round 2
                           ↓
                   ... (max 3 iterations)
                           ↓
                   Approved → Phase 6
                   Rejected (3x) → Escalate to Human
```

### Parameters

| Parameter | Value |
|-----------|-------|
| Maximum Iterations | 3 |
| Reviewer | LLM (self-critique) |
| Human Escalation | Optional (when questions remain or 3x rejected) |

### Feedback Structure

Each review iteration produces:

| Field | Type | Purpose |
|-------|------|---------|
| `issues` | list[str] | Blocking problems - must be fixed |
| `suggestions` | list[str] | Non-blocking improvements - recommended |
| `questions` | list[str] | Questions for human review |
| `status` | approved/rejected/needs-human | Review outcome |
| `summary` | str | Brief explanation |

### Escalation Criteria

Automatic escalation to human occurs when:
1. **Questions remain** after max iterations
2. **Issues unresolved** after 3 review rounds
3. **Explicit `needs-human` status** from reviewer

### Implementation

Implemented in `governance/application/use_cases/phase5_iterative_review.py`:
- `Phase5ReviewFeedback` - Structured feedback per iteration
- `Phase5ReviewState` - Tracks iteration count, feedback history, plan versions
- `record_review_feedback()` - Records feedback and determines next state
- `finalize_review()` - Returns approved/escalated result

### SESSION_STATE Fields

```yaml
Phase5Review:
  Iteration: 1..3
  PlanVersion: 1..N
  Status: pending | approved | escalated-to-human
  FeedbackHistory:
    - Iteration: 1
      Issues: ["Missing test coverage"]
      Suggestions: ["Add integration tests"]
      Questions: []
      Status: rejected
 ```

## Gate Requirements for Code Generation

Phase 3 API validation is **optional** and does NOT block code generation. The gates that MUST pass before code output:

| Gate | Phase | Required? | Condition |
|------|-------|-----------|-----------|
| P5-Architecture | 5 | **Always** | Must be `approved` (after iterative review) |
| P5.3-TestQuality | 5.3 | **Always** | Must be `pass` or `pass-with-exceptions` |
| P5.4-BusinessRules | 5.4 | Conditional | Only if Phase 1.5 was executed |
| P5.5-TechnicalDebt | 5.5 | Optional | Only when explicitly proposed |
| P5.6-RollbackSafety | 5.6 | Conditional | When rollback-sensitive changes exist |
| P6-ImplementationQA | 6 | **Always** | Must be `ready-for-pr` |

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
