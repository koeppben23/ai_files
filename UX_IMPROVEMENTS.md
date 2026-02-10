# UX Improvements (Non-Behavioral)

This branch intentionally preserves runtime behavior identical to `main`.

The only accepted changes in this scope are UX-focused and non-behavioral:

- clearer operator-facing phrasing in responses
- better scanability of status output
- deterministic wording for recovery hints
- no change to gate semantics, evidence contracts, or execution flow

Guardrail:

- if a change alters blockers, gate transitions, evidence requirements, or helper execution order,
  it is out of scope for this branch and must be implemented in a separate behavior-change branch.
