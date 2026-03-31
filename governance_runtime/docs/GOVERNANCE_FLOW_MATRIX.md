# Governance Flow Matrix

This matrix is the canonical human-readable reference for governance rail routing.
It mirrors the deterministic resolver behavior in
`governance_runtime/application/services/transition_model.py`.

## Phase 4

| Phase | Active Gate | Condition | Next Action | Notes |
|---|---|---|---|---|
| 4 | Ticket Input Gate | ticket/task not persisted | `/ticket` | `/ticket` requires hydrated session; bootstrap guidance points to `/hydrate` first and `/review` remains read-only alternative |

## Hydration Preconditions

| Scope | Condition | Next Action | Enforcement |
|---|---|---|---|
| Phase 4 mutating rail | `SessionHydration.status != hydrated` | `/hydrate` | hard-blocked (`/ticket` returns blocked) |
| Phase 5 mutating rail | `SessionHydration.status != hydrated` | `/hydrate` | hard-blocked (`/plan` returns blocked) |
| Phase 4 read-only rail | `session_hydrated != true` | `/hydrate` | soft fail-closed in rail contract (`/review`) |

## Phase 5

| Phase | Active Gate | Condition | Next Action | Notes |
|---|---|---|---|---|
| 5 | Plan Record Preparation Gate | `plan_record_versions < 1` | `/plan` | plan-record required |
| 5 | any other Phase-5 gate | normal progress | `/continue` | routing/progress state |
| 5.4 | Business Rules Validation | all missing surfaces are `filtered_non_business` and no invalid/source/render/segmentation defects | `not-applicable` gate result | phase advances to Phase 6 via `/continue` |
| 5.4 | Business Rules Validation | mixed/real business-rule gaps or invalid rules | `gap-detected` gate result | remains blocked in Phase 5.4 |

## Phase 6

| Phase | Active Gate | Condition | Next Action | Kind |
|---|---|---|---|---|
| 6 | Rework Clarification Gate | no clarification input | `chat` | blocked |
| 6 | Rework Clarification Gate | classification `scope_change` | `/ticket` | normal |
| 6 | Rework Clarification Gate | classification `plan_change` | `/plan` | normal |
| 6 | Rework Clarification Gate | classification `clarification_only` | `/continue` | normal |
| 6 | Evidence Presentation Gate | waiting final review decision | `/review-decision` | normal |
| 6 | Workflow Complete | governance approved | `/implement` | terminal |
| 6 | Implementation Rework Clarification Gate | implementation clarification present | `/implement` | normal |
| 6 | Implementation Started | execution running | `execute` | implementation |
| 6 | Implementation Execution In Progress | loop active | `/continue` | normal |
| 6 | Implementation Self Review | loop active | `/continue` | normal |
| 6 | Implementation Revision | loop active | `/continue` | normal |
| 6 | Implementation Verification | loop active | `/continue` | normal |
| 6 | Implementation Review Complete | loop active | `/continue` | normal |
| 6 | Implementation Blocked | implementation blocked | `/implement` | blocked |
| 6 | Implementation Presentation Gate | waiting implementation decision | `/implementation-decision` | normal |

## Global Status Overrides

| Status | Next Action | Kind | Reason |
|---|---|---|---|
| `error` | `/continue` | recovery | error-status |
| `blocked` | `/continue` | blocked | blocked-status |

## Read-Only Review Rail

- `/review` is read-only and does not mutate governance session state.
- `/review` requires hydrated session context and must fail closed to `/hydrate` when not hydrated.
- In Phase 4 guidance, bootstrap output points to `/hydrate` first; once hydrated, `/review` remains the explicit read-only alternative to `/ticket`.
- `/review` and `/review-decision` are distinct rails: `/review` is analysis-only; `/review-decision` mutates state in Phase 6 evidence presentation.

## Verification Matrix Tests

- `tests/test_implement_start_entrypoint.py::TestImplementFlowTruthMatrix`
  - happy: new hotspot file is created and implementation passes
  - bad: executor failure blocks
  - corner: targeted-check failure blocks despite domain diffs
  - edge: hotspot coverage missing blocks despite unrelated diffs
