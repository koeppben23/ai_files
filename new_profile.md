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
5. shared principal-governance delegation block:
   - `## Shared Principal Governance Contracts (Binding)`
   - `rules.principal-excellence.md`
   - `rules.risk-tiering.md`
   - `rules.scorecard-calibration.md`
   - loaded-addon tracking keys under `SESSION_STATE.LoadedRulebooks.addons.*`

Exception for shared contract rulebooks themselves:
- If `profile_key` is one of `principal-excellence`, `risk-tiering`, `scorecard-calibration`,
  generate the corresponding canonical shared contract section directly instead of delegation.

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

- shared contract delegation block + references to all three shared rulebooks
- loaded-addon tracking keys for shared contracts:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`

For shared contract rulebooks (`principal-excellence`, `risk-tiering`, `scorecard-calibration`):
- ensure the generated shared rulebook includes its canonical contract section and required warnings/thresholds.

If any checklist item fails, completion status MUST be `not-verified`.

---

## Suggested Conventional Commit

- `feat(governance): add <profile_key> principal profile rulebook`
