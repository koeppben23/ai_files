# Planning Rail (Guidance)

This rail is non-binding guidance for the `/plan` command.

## How /plan works

`/plan` is the productive planning rail. When invoked without explicit `--plan-text`, it:

1. Reads the persisted Ticket/Task from session state
2. Loads the plan mandate from `governance_mandates.v1.schema.json` (fail-closed)
3. Loads the effective authoring policy from active rulebooks/addons (fail-closed)
4. Calls the Desktop LLM (`OPENCODE_PLAN_LLM_CMD`) to generate a structured plan
5. Validates the LLM response against `planOutputSchema` (fail-closed)
6. Converts the structured plan to markdown for the existing review chain
7. Runs the Phase-5 self-review loop (max 3 iterations)
8. Compiles to requirement contracts
9. Persists plan-record evidence only when valid

## Planning guidance

- Prefer evidence-backed plans with explicit assumptions.
- Keep scope minimal and reviewable.
- Call out unknowns and dependency risks early.
- Reference kernel/state artifacts instead of redefining runtime rules.
- A plan that cannot be reviewed is not a plan — it is speculation.

## Fail-closed behavior

All four gates must pass for plan generation to proceed:
- **Mandate schema**: must be loadable with valid `plan_mandate` block
- **Effective policy**: must be buildable from active rulebooks/addons
- **planOutputSchema**: must be present in the mandates schema
- **Validator**: `validate_plan_response` must be importable

If any gate fails, `/plan` blocks with a specific `reason_code`.
