# Binding Evidence Naming

This note defines the canonical binding-evidence keys used by runtime outputs.

## Canonical keys

- `pipeline_mode`: `true` when `pipeline_mode` is active for the invoking flow, else `false`.
- `binding_role`: role requested from resolver (`execution` or `review`).
- `binding_source`: origin of selected binding (`active_chat_binding`, `env:AI_GOVERNANCE_EXECUTION_BINDING`, `env:AI_GOVERNANCE_REVIEW_BINDING`, or explicit override source).

## State surfaces

- Phase 5 state:
  - `phase5_plan_execution_pipeline_mode`
  - `phase5_plan_execution_binding_role`
  - `phase5_plan_execution_binding_source`
  - `phase5_review_pipeline_mode`
  - `phase5_review_binding_role`
  - `phase5_review_binding_source`
- Phase 6 state:
  - `phase6_review_pipeline_mode`
  - `phase6_review_binding_role`
  - `phase6_review_binding_source`
- Implementation state:
  - `implementation_pipeline_mode`
  - `implementation_binding_role`
  - `implementation_binding_source`

## Event surfaces

- Implementation events include canonical keys on:
  - `IMPLEMENTATION_STARTED`
  - `IMPLEMENTATION_BLOCKED_PRECHECK`
  - `IMPLEMENTATION_BLOCKED_VALIDATION`
- Phase 5 persisted event includes:
  - `plan_execution_pipeline_mode`
  - `plan_execution_binding_source`
  - `review_pipeline_mode`
  - `review_binding_source`
- Phase 6 review iteration event includes:
  - `llm_review_pipeline_mode`
  - `llm_review_binding_role`
  - `llm_review_binding_source`

## Contract rules

- Direct mode ignores environment bindings and may emit `active_chat_binding` source.
- Pipeline mode requires both `AI_GOVERNANCE_EXECUTION_BINDING` and `AI_GOVERNANCE_REVIEW_BINDING`.
- Review paths must never emit execution binding source.
- Execution paths must never emit review binding source.
