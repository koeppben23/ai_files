# Canonical Field Ownership

Purpose: prevent SSOT drift by declaring ownership of terms and contracts.

## Kernel-owned only (reference-only in MD)

- Phase IDs
- Gate enums and statuses
- Reason codes
- Transition IDs
- SESSION_STATE keys and invariant rules
- Blocked defaults and recovery triggers

Default rewrite role:
- If a field/contract is Kernel-owned only, the MD role is **Reference-only**.

## MD-allowed (policy/UX only)

- Short descriptions and operator guidance
- Policy-only Do/Don't rules
- UX framing and explanation wording
- Escalation phrasing and operator prompts

## Enforcement rule

- Kernel-owned rules must be referenced, not re-specified, in Markdown.
