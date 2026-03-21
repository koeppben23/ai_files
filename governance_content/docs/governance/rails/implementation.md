# Implementation Rail (Guidance)

This rail is non-binding guidance for the `/implement` command.

## How /implement works

`/implement` starts execution of the approved implementation plan after Phase 6 governance review approval.

Prerequisites (all must be true):
- Phase 6 active
- Review decision is `approve` (Workflow Complete)
- Plan record exists (plan-record.json with at least 1 version)
- Compiled requirement contracts exist (compiled_requirements.json)

Flow:
1. Reads plan-record and compiled requirements
2. Loads developer mandate and effective authoring policy (fail-closed)
3. Writes LLM context file (ticket, task, plan, hotspots, constraints)
4. Invokes the Desktop LLM executor (`OPENCODE_IMPLEMENT_LLM_CMD`)
5. LLM response validated against `developerOutputSchema` (fail-closed)
6. Runs targeted checks (pytest on acceptance tests)
7. Validates: domain files changed, plan coverage met, targeted checks pass
8. Routes to Implementation Review Complete or Implementation Blocked

## Implementation guidance

- Follow existing repository conventions first.
- Prefer additive, low-risk changes.
- Keep diffs coherent and reversible.
- Separate behavior changes from refactors where practical.
- Build changes that can withstand falsification-first review.
