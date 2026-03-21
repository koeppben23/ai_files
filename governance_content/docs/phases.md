# End-to-End Phases

This document is a detailed phase map that was previously embedded in README.md.
Authority boundary: policy, gate semantics, and routing are owned by kernel code plus kernel-owned configs/schemas; this file is explanatory and does not widen kernel behavior.

SSOT: `${SPEC_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.  `governance_content/docs/phases.md` is explanatory only — it does not widen kernel behavior.
Kernel: `governance_runtime/kernel/*` is the canonical control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.
Phase `1.3` is mandatory before every phase `>=2`.

## Customer View (Short)

- Phase 0 triggers bootstrap and initializes the governance runtime workspace.
- Phase 1.1 (Bootstrap) validates install/path/session prerequisites before work proceeds. It sets the `Workspace Ready Gate`.
- Phase 1 (Workspace Persistence) persists bootstrap artifacts and verifies workspace state.
- Phase 1.2 (Activation Intent) captures activation intent with sha256 evidence.
- Phase 1.3 (Rulebook Load) loads core/profile/templates/addons rulebooks with evidence before routing to Phase 2.
- Phase 2 (Repository Discovery) builds repo context and reusable decision artifacts.
- Phase 2.1 (Decision Pack) creates the Decision Pack and resolves Phase 1.5 routing.
- Phase 1.5 (Business Rules Discovery, optional) — phase 1.5 is an optional business-rules routing branch — extracts business rules; once executed, Phase 5.4 becomes mandatory.
- Phase 3A (API Inventory) inventories external API artifacts — always executed, may record `not-applicable`.
- Phase 3B-1 / 3B-2 (API Validation) run only when APIs are detected.
- Phase 4 (Ticket Intake) produces the concrete implementation plan; `/review` is a read-only rail entrypoint for feedback.
- Phase 5 — `/plan` auto-generates a plan from the persisted ticket/task via Desktop LLM, runs self-review (min 1, max 3 iterations), compiles requirement contracts, and persists plan-record evidence. User may also provide plan text explicitly via `--plan-text`.
- Phase 5.3 / 5.4 / 5.5 / 5.6 are conditional gates following Phase 5.
- Phase 6 (Implementation) runs internal review loop, then presents evidence. Final decision via `/review-decision` (approve | changes_requested | reject). `/continue` does NOT advance past the Evidence Presentation Gate.

## Canonical Flow

```
0 → 1.1 → 1 → 1.2 → 1.3 → 2 → 2.1
  After 2.1: if business_rules_execute → 1.5 → 3A; else → 3A
  Phase 3A: if no_apis → 4; else → 3B-1 → 3B-2 → 4
  Main execution: 4 → 5 → 5.3 → [5.4] → [5.5] → [5.6] → 6
  Phase 6 internal: Implementation Internal Review (max 3 iterations)
    → Evidence Presentation Gate
    → /review-decision <approve|changes_requested|reject>
      approve     → Workflow Complete (terminal)
      changes_requested → Rework Clarification Gate (Phase 6)
      reject      → Phase 4 (Ticket Input Gate)
```

## Full Phase Map

| Phase | Token | Active Gate | Gate / blocked behavior |
|-------|-------|-----------|------------------------|
| Bootstrap (Phase 0) | `0-None` | Bootstrap Required | Route to 1.1 unconditionally. If bootstrap evidence invalid/missing, workflow BLOCKED. |
| Bootstrap | `1.1-Bootstrap` | Workspace Ready Gate | Complete workspace persistence and pointer verification. |
| Workspace Persistence | `1-WorkspacePersistence` | Persistence Gate | Persist bootstrap artifacts and verify workspace state. |
| Activation Intent | `1.2-ActivationIntent` | Activation Intent | Exit requires: `Intent.Path`, `Intent.Sha256`, `Intent.EffectiveScope`. Auto-routes to 1.3. |
| Rulebook Load | `1.3-RulebookLoad` | Rulebook Load Gate | Exit requires: `LoadedRulebooks.core`, `LoadedRulebooks.profile`, `RulebookLoadEvidence.core`, `RulebookLoadEvidence.profile`, `ActiveProfile`, `AddonsEvidence`. |
| Repo Discovery | `2-RepoDiscovery` | Repo Discovery | Non-gate; missing artifacts trigger BLOCKED continuation. Exit requires: `RepoDiscovery.Completed`, `RepoDiscovery.RepoCacheFile`, `RepoDiscovery.RepoMapDigestFile`. |
| Decision Pack | `2.1-DecisionPack` | Decision Pack | Routing checkpoint only. Transitions: `business_rules_execute` → 1.5; `default` → 3A. |
| Business Rules Discovery (optional) | `1.5-BusinessRules` | Business Rules Bootstrap | Optional; only entered when `business_rules_execute` transition fires. Exit requires: `BusinessRules.Inventory.sha256`. Once executed, Phase 5.4 is mandatory. |
| API Inventory | `3A-API-Inventory` | API Inventory | Always executed. Transitions: `no_apis` → 4; `default` → 3B-1. Exit requires: `APIInventory.Status`. |
| API Logical Validation | `3B-1` | API Logical Validation | **Conditional**: only when APIs detected. Auto-routes to 3B-2. |
| Contract Validation | `3B-2` | Contract Validation | **Conditional**: only when APIs detected. Auto-routes to 4. |
| Ticket Intake / Planning | `4` | Ticket Input Gate | Non-gate for routing. Code output blocked until gates pass. `/review` is a read-only rail entrypoint without state change. Transitions: `ticket_present` → 5; `default` → stay in 4. |
| Architecture Review | `5-ArchitectureReview` | Plan Record Preparation Gate / Architecture Review Gate | `/plan` auto-generates plan from Ticket/Task via Desktop LLM (fail-closed: mandate, policy, schema required). Self-review loop runs min 1, max 3 iterations. Transitions: `plan_record_missing` → stay; `self_review_iterations_pending` → stay; `self_review_iterations_met` → 5.3. |
| Test Quality Review | `5.3-TestQuality` | Test Quality Gate | Unconditional. Transitions: `business_rules_gate_required` → 5.4; `technical_debt_proposed` → 5.5; `rollback_required` → 5.6; `default` → 6. |
| Business Rules Compliance | `5.4-BusinessRules` | Business Rules Validation | Conditional — only active when Phase 1.5 executed. Transitions: `technical_debt_proposed` → 5.5; `rollback_required` → 5.6; `default` → 6. |
| Technical Debt Review | `5.5-TechnicalDebt` | Technical Debt Review | Always checked (may be `not-applicable`). Transitions: `rollback_required` → 5.6; `default` → 6. |
| Rollback Safety | `5.6-RollbackSafety` | Rollback Safety Review | Conditional — when rollback-sensitive changes exist. Always routes to 6. |
| Implementation QA | `6-PostFlight` | Implementation Internal Review → Evidence Presentation Gate | Final gate. Internal review loop (max 3). Transitions: `implementation_review_complete` → Evidence Presentation Gate; `implementation_accepted` → 6; `implementation_blocked` → 6; `workflow_approved` → Workflow Complete; `review_rejected` → 4; `review_changes_requested` → Rework Clarification Gate. |

## Phase Transitions (from phase_api.yaml)

### Routing Priority
Kernel routing follows one deterministic priority chain:
1. first matching `specific` transition
2. otherwise `default`
3. otherwise `next`
4. otherwise terminal/config error

### Key Transition Table

| From | To | When | Source |
|------|----|------|--------|
| 0 | 1.1 | always | implicit |
| 1.1 | 1 | always | implicit |
| 1 | 1.2 | always | implicit |
| 1.2 | 1.3 | default | phase-1.2-to-1.3-auto |
| 1.3 | 2 | always | implicit |
| 2 | 2.1 | always | implicit |
| 2.1 | 1.5 | business_rules_execute | phase-1.5-routing-required |
| 2.1 | 3A | default | phase-2.1-to-3a |
| 1.5 | 3A | default | phase-1.5-to-3a |
| 3A | 4 | no_apis | phase-3a-not-applicable-to-phase4 |
| 3A | 3B-1 | default | phase-3a-to-3b1 |
| 3B-1 | 3B-2 | default | phase-3b1-to-3b2 |
| 3B-2 | 4 | default | phase-3b2-to-4 |
| 4 | 5 | ticket_present | phase-4-to-5-ticket-intake |
| 4 | 4 | default (stay) | phase-4-awaiting-ticket-intake |
| 5 | 5 | plan_record_missing | phase-5-plan-record-prep-required |
| 5 | 5 | self_review_iterations_pending | phase-5-self-review-required |
| 5 | 5.3 | self_review_iterations_met | phase-5-architecture-review-ready |
| 5.3 | 5.4 | business_rules_gate_required | phase-5.3-to-5.4 |
| 5.3 | 5.5 | technical_debt_proposed | phase-5.3-to-5.5 |
| 5.3 | 5.6 | rollback_required | phase-5.3-to-5.6 |
| 5.3 | 6 | default | phase-5.3-to-6 |
| 5.4 | 5.5 | technical_debt_proposed | phase-5.4-to-5.5 |
| 5.4 | 5.6 | rollback_required | phase-5.4-to-5.6 |
| 5.4 | 6 | default | phase-5.4-to-6 |
| 5.5 | 5.6 | rollback_required | phase-5.5-to-5.6 |
| 5.5 | 6 | default | phase-5.5-to-6 |
| 5.6 | 6 | default | phase-5.6-to-6 |
| 6 | 4 | review_rejected | phase-6-rejected-to-phase4 |
| 6 | 6 | implementation_review_complete | phase-6-ready-for-user-review (Evidence Presentation Gate) |

## Phase-Coupled Persistence (Outside Repository)

**SSOT Enforcement (Binding):** Persistence is mandatory and enforced by the kernel (not by LLM output).

| Phase | Artifact | Key Session State Fields |
|-------|----------|-------------------------|
| Phase 1.1 | Bootstrap session | `Preflight.BuildToolchain.DetectedTools`, `ObservedAt` |
| Phase 1 | Workspace persistence | `PersistenceGatePassed`, `PointerFile` |
| Phase 1.2 | Activation intent | `Intent.Path`, `Intent.Sha256`, `Intent.EffectiveScope` |
| Phase 1.3 | Rulebook load | `LoadedRulebooks.core`, `LoadedRulebooks.profile`, `ActiveProfile`, `AddonsEvidence` |
| Phase 2 | Discovery | `RepoDiscovery.Completed`, `RepoDiscovery.RepoCacheFile`, `RepoDiscovery.RepoMapDigestFile`, `RepoMapDigest`, `DecisionDrivers`, `WorkingSet`, `TouchedSurface` |
| Phase 2 Step 3a | CodebaseContext | `CodebaseContext.ExistingAbstractions`, `CodebaseContext.DependencyGraph`, `CodebaseContext.PatternFingerprint`, `CodebaseContext.TechnicalDebtMarkers` |
| Phase 2 Step 3b | BuildToolchain | `BuildToolchain.CompileAvailable`, `BuildToolchain.CompileCmd`, `BuildToolchain.TestAvailable`, `BuildToolchain.TestCmd`, `BuildToolchain.FullVerifyCmd`, `BuildToolchain.BuildSystem`, `BuildToolchain.MissingTool` |
| Phase 2.1 | Decision Pack | `DecisionPackFile`, routing decision state |
| Phase 1.5 | Business Rules | `BusinessRules.Inventory.sha256`, `BusinessRules.Status` |
| Phase 4 | Ticket Intake | `Ticket.Digest`, `FeatureComplexity.Class`, `FeatureComplexity.Reason`, `FeatureComplexity.PlanningDepth` |
| Phase 5 | Plan Record | `PlanRecordVersion`, `Gates.P5-Architecture`, `Phase5Review.Iteration`, `Phase5Review.PlanVersion`, `Phase5Review.Status`, `Phase5Review.FeedbackHistory` |
| Phase 5.3 | Test Quality | `Gates.P5.3-TestQuality` |
| Phase 5.4 | Business Rules Compliance | `Gates.P5.4-BusinessRules` (mandatory only if Phase 1.5 executed) |
| Phase 5.5 | Technical Debt | `Gates.P5.5-TechnicalDebt` |
| Phase 5.6 | Rollback Safety | `Gates.P5.6-RollbackSafety` |
| Phase 6 | Implementation QA | `Gates.P6-ImplementationQA`, `BuildEvidence.status`, `BuildEvidence.CompileResult`, `BuildEvidence.TestResult`, `BuildEvidence.IterationsUsed` |

## Kernel CLI Entrypoints

These are the authoritative CLI commands that drive governance. Every phase transition uses one of these:

| Entrypoint | Module | Purpose |
|-----------|--------|---------|
| Bootstrap | `cli.bootstrap init` | Initializes workspace, runs persistence hook |
| `/continue` | `governance_runtime.entrypoints.session_reader --materialize` | Advances routing, runs Phase 6 internal loop |
| `/ticket` | `governance_runtime.entrypoints.phase4_intake_persist` | Persists ticket/task intake evidence |
| `/plan` | `governance_runtime.entrypoints.phase5_plan_record_persist` | Auto-generates plan from Ticket/Task via LLM, runs self-review, persists plan-record evidence |
| `/implement` | `governance_runtime.entrypoints.implement_start` | Starts implementation execution (Phase 6) |
| `/review-decision` | `governance_runtime.entrypoints.review_decision_persist --decision <approve\|changes_requested\|reject>` | Final review decision at Evidence Presentation Gate |

## Gate Requirements for Code Generation

| Gate | Phase | Required? | Condition |
|------|-------|-----------|-----------|
| P5-Architecture | 5 | Unconditional | Requires `approved` status after self-review iterations met (min 1, max 3) |
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
- `/plan` is the productive planning rail: auto-generates plan from ticket/task, reviews, and persists.
- `/continue` and `/review` remain read-only rails and do not mutate intake/plan evidence.
- `FeatureComplexity` can be persisted as supporting metadata but does not unlock Phase 4 on its own.

## Phase 5 Plan Generation and Self-Review

Phase 5 runs an integrated plan-generation and self-review loop:

1. **Plan generation:** `/plan` reads the persisted `Ticket`/`Task` from session state and generates a structured plan via the Desktop LLM. This requires:
   - `OPENCODE_PLAN_LLM_CMD` (or fallback `OPENCODE_IMPLEMENT_LLM_CMD`) — executor must be configured
   - `governance_mandates.v1.schema.json` must be loadable with valid `plan_mandate` block
   - Effective authoring policy must be buildable from active rulebooks/addons
   - LLM response must conform to `planOutputSchema` (fail-closed on any violation)
2. **Self-review loop:** The generated plan is reviewed (max 3 iterations, min 1). Each iteration runs LLM review and mechanical section checks.
3. **Contract compilation:** Final plan is compiled to requirement contracts (merging ticket, task, and plan text).
4. **Persistence:** Plan record and compiled contracts are persisted only when valid.

Constraints (from `phase_api.yaml`):
- `output_policy.min_self_review_iterations: 1`
- Maximum 3 review iterations
- Early-stop: only when digest unchanged after minimum iterations
- Hard-stop: when max iterations reached
- Output is always `draft_not_review_ready` on first output
- Forbidden output classes during Phase 5: `implementation`, `patch`, `diff`, `code_delivery`

## Phase 6 Review Decision

At the Evidence Presentation Gate (`implementation_review_complete`), the operator must run `/review-decision`:

| Decision | Effect |
|----------|--------|
| `approve` | Workflow Complete — terminal state within Phase 6 (`workflow_complete=true`) |
| `changes_requested` | Enter Rework Clarification Gate in Phase 6 — clarify in chat first, then run exactly one directed rail (`/ticket`, `/plan`, or `/continue`) |
| `reject` | Back to Phase 4 — restart from planning (Ticket Input Gate) |

**Key:** `/continue` does NOT advance past the Evidence Presentation Gate. The operator must explicitly run `/review-decision`.

## Phase 3 Routing (API Detection)

Phase 3 is **conditionally executed** based on API presence:

| Condition | Phase 3A | Phase 3B-1/3B-2 | Flow |
|-----------|----------|------------------|------|
| No APIs in scope | Executed (not-applicable) | Skipped | 3A → 4 directly |
| APIs detected | Executed | Executed | 3A → 3B-1 → 3B-2 → 4 |

## Routing Priority Semantics

Kernel routing follows one deterministic priority chain:

1. first matching `specific` transition
2. otherwise `default`
3. otherwise `next`
4. otherwise terminal/config error

If multiple `specific` transitions match, the first declared transition wins.
