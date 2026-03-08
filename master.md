<!-- rail-classification: GUIDANCE, MULTI-PHASE -->

This file is the multi-phase interpretation guide for governance behavior.
SSOT is kernel and schema code; Markdown provides routing and operative guardrails only.

<authority>

## Authority

| Area | SSOT source |
|------|-------------|
| Routing, transitions, validation | `${COMMANDS_HOME}/phase_api.yaml`, `governance/kernel/*` |
| Session-state shape and invariants | `SESSION_STATE_SCHEMA.md`, `governance/assets/schemas/*` |
| Response envelope and renderer behavior | `governance/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json` |
| Blocked reason catalog | `governance/assets/reasons/blocked_reason_catalog.yaml` |
| Path and persistence invariants | `governance/engine/session_state_invariants.py` |

</authority>

---

<phase-routing>

## Phase Routing Table

| Phase | Name | Key constraint |
|------|------|----------------|
| 0 | Bootstrap | If prerequisites are missing, return BLOCKED and request restatement |
| 1.2 | Profile Detection | Profile selection is kernel-enforced |
| 1.3 | Core Rules Activation | Mandatory before every phase >=2 |
| 1.4 | Templates and Addons | Activation and merge behavior are kernel-owned |
| 2 | Repo Discovery | Repo evidence wins over stale workspace assumptions |
| 4 | Planning | Build a ticket record and implementation plan with risk review |
| 5 | Review Gate | Review gate only; implementation output is not permitted during Phase 5 |
| 5.3 | Test Quality Review | CRITICAL gate; test-quality-pass must proceed to Phase 6 |
| 6 | Implementation QA | Implementation begins only after Phase 5 gates pass |

</phase-routing>

---

<operative-constraints>

## Bootstrap minimum

- If bootstrap prerequisites are missing, emit `BLOCKED` and ask for the minimum missing evidence.
- Persist artifacts under `${CONFIG_ROOT}`-derived workspace paths, never inside repo working tree.

## Planning discipline

- Planning output includes ticket record, options, recommendation, and confidence.
- If ambiguity remains, request clarification before implementation.

## Phase 5 review gate discipline

Code-producing output is not permitted during Phase 5.
Phase 5 is a review gate only, and implementation starts in Phase 6.

Rule A - implementation-intent prohibition:
- Output classes classified as implementation artifacts or implementation-intent are forbidden in Phase 5.
- Canonical allow/deny classes are kernel-owned in `output_policy` at token `"5"`.

Rule B - plan self-review requirement:
- The first Phase-5 plan is draft-quality.
- At least one internal self-review iteration is required before presenting review-ready output.
- Minimum self-review iterations are kernel-owned in `output_policy.plan_discipline`.

## Review and quality checkpoints

- Architecture review verifies conventions, dependency integrity, and risk posture.
- Phase 5.3 is CRITICAL and confirms implementation readiness.

</operative-constraints>

---

<presentation-advisory>

## Presentation advisory

Response schema and rendering are defined outside this file.
`master.md` does not redefine response shape.

</presentation-advisory>

---
