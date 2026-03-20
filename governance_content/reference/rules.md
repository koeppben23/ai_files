<!-- rail-classification: CONSTRAINT-SET, CROSS-PHASE -->

This file defines stack-agnostic technical, evidence, and quality constraints.
Routing semantics are in `master.md`; runtime behavior is kernel/schema-owned.

<authority>

## Authority

| Area | SSOT source |
|------|-------------|
| Routing / validation / transitions | `${COMMANDS_HOME}/phase_api.yaml` and `governance_runtime/kernel/*` |
| Session-state shape and invariants | `SESSION_STATE_SCHEMA.md` and `governance_runtime/assets/schemas/*` |
| Response envelope and presentation | `governance_runtime/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json` |
| Blocked reason catalog | `governance_runtime/assets/config/blocked_reason_catalog.yaml` |
| Persistence artifact contracts | `governance_runtime/assets/config/persistence_artifacts.yaml` |

</authority>

---

<operative-constraints>

## Governance scope model

If the repository is a monorepo or contains multiple stacks/components, establish a **Component Scope** before any code-producing work.

Component Scope is a bounded set of repo-relative paths that define ownership and limits.

Rules:
- If code-producing work is requested without explicit Component Scope, return blocked and request clarification.
- Planning and review operate against the Working Set by default.
- If scope expands, update Touched Surface and record evidence.
- Fast Path is allowed only when scope and evidence are deterministic.

## Profile and rulebook activation

- In ambiguity, stay in planning mode or return blocked before code-producing work.
- Active profile and activation evidence must be recorded in session state.
- Rulebook precedence, merge, and activation behavior are kernel-owned in `governance_runtime/kernel/*`.

## Review and quality constraints

- Security and privacy checks are minimum sanity checks, not a full security review.
- Cross-repo impact, scorecard, and review-of-review checks follow kernel-owned gate contracts in `governance_runtime/kernel/*`.
- Business logic belongs in domain models/domain type boundaries, not adapters.
- Test design must remain deterministic and evidence-backed.

## Mode mandates

### Authoring mandate

- Produce the smallest correct solution that satisfies active contract constraints.
- Stay within documented public surface boundaries and avoid unsupported workflow invention.
- Prefer deterministic, testable paths over speculative optimization.

### Review mandate

- Attempt to falsify before approving; do not assume correctness without evidence.
- Confirm only claims backed by code, contracts, tests, or explicit architecture policy.
- Actively check for contract drift, logic gaps, cross-OS risk, silent fallback leakage, and test gaps.
- Prefer fail-closed outcomes when evidence is incomplete.

## Traceability

- Ticket records and business-rules traces must be attributable and current.
- Build and test evidence must map to the active gate decision.

</operative-constraints>

---

<evidence-rules>

## Evidence rules

### Evidence ladder

Evidence precedence is kernel-owned in `governance_runtime/kernel/*`; this file preserves the rule intent.

### Strict evidence mode (default)

- If evidence is not possible, the workflow explicitly states:
  > "Not provable with the provided artifacts."

Gate artifacts must be complete enough to justify each gate outcome.

</evidence-rules>

---

<presentation-advisory>

## Presentation advisory

Rendering schema is external to this file.

Operative rules:
1. Responses expose exactly one actionable next step.
2. One primary blocker is surfaced first; recovery stays deterministic.
3. Required-gate missing evidence is treated as blocked, not warn.
4. Presentation mode does not change gate/evidence semantics.

</presentation-advisory>

---
