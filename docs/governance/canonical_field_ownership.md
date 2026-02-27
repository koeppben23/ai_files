# Canonical Field Ownership

Purpose: prevent SSOT drift by declaring ownership of terms and contracts.

## Kernel-owned only (reference-only in MD)

- Phase IDs (from `phase_api.yaml`)
- Gate enums and statuses (kernel gate evaluators)
- Reason codes (from `governance/assets/reasons/*.yaml`)
- Transition IDs (kernel trace)
- SESSION_STATE keys and invariant rules (session schema + invariants)
- Blocked defaults and recovery triggers (kernel enforcement)

Default rewrite role:
- If a field/contract is Kernel-owned only, the MD role is **Reference-only**.

## MD-allowed (policy/UX only)

- Short descriptions and operator guidance
- Policy-only Do/Don't rules
- UX framing and explanation wording
- Escalation phrasing and operator prompts

## Enforcement rule

- Kernel-owned rules must be referenced, not re-specified, in Markdown.

## SSOT guard artifacts

- `docs/governance/kernel_vs_docs_matrix.csv`
- `governance/assets/catalogs/SSOT_GUARD_RULES.json`
