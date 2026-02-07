# Governance Factory - New Profile

Purpose (binding):
- Create a new `profiles/rules.<profile>.md` rulebook that is immediately principal-grade and compatible with all current governance contracts.

Scope:
- This command defines how profile rulebooks are generated.
- It does not modify `master.md` precedence.

---

## Required Input (Binding)

When invoking this command, provide at least:

- `profile_key`: canonical profile name (for `rules.<profile_key>.md`)
- `stack_scope`: technology/domain scope
- `activation_signals`: evidence signals that justify profile applicability
- `quality_focus`: business/test quality priorities
- `blocking_policy`: explicit fail-closed behavior for missing required contracts

If required input is missing, return `BLOCKED` with missing fields.

---

## Generation Contract (Binding)

Generated profile rulebooks MUST include:

1. clear precedence statement (`master.md` > `rules.md` > profile)
2. deterministic applicability section
3. architecture and test-quality expectations
4. BuildEvidence requirement language
5. principal baseline sections:
   - `## Principal Excellence Contract (Binding)`
   - `## Principal Hardening v2.1 - Standard Risk Tiering (Binding)`
   - `## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)`

Claims without evidence mapping MUST be marked `not-verified`.

---

## Output Files (Binding)

This command MUST produce:

- `profiles/rules.<profile_key>.md`

Optional:

- changelog note in `[Unreleased]` when requested by operator.

---

## Principal Conformance Checklist (Binding)

Before finalizing, verify generated profile contains:

- canonical risk tiers (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`)
- score thresholds (`0.80`, `0.85`, `0.90`)
- calibration warning code (`WARN-SCORECARD-CALIBRATION-INCOMPLETE`)
- missing-evidence warning (`WARN-PRINCIPAL-EVIDENCE-MISSING`)
- required `SESSION_STATE` scorecard and `RiskTiering` shape snippets

If any checklist item fails, completion status MUST be `not-verified`.

---

## Suggested Conventional Commit

- `feat(governance): add <profile_key> principal profile rulebook`
