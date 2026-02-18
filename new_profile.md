# Governance Factory - New Profile

Purpose (binding):
- Create a new `profiles/rules_<profile>.md` rulebook (preferred naming) that is immediately principal-grade and compatible with all current governance contracts.

Scope:
- This command defines how profile rulebooks are generated.
- It does not modify `master.md` precedence.

---

## Required Input (Binding)

When invoking this command, provide at least:

- `profile_key`: canonical profile name (preferred output: `rules_<profile_key>.md`; legacy alias accepted)
- `stack_scope`: technology/domain scope
- `applicability_signals`: evidence signals that justify profile applicability (descriptive only)
- `quality_focus`: business/test quality priorities
- `blocking_policy`: explicit fail-closed behavior for missing required contracts

If required input is missing, return `BLOCKED` with missing fields.

---

## Generation Contract (Binding)

Generated profile rulebooks MUST include:

1. canonical precedence reference to `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` (do not redefine local precedence order)
2. deterministic applicability section
3. architecture and test-quality expectations
4. canonical evidence-path requirement language
   - include explicit paths used by runtime diagnostics/contracts:
     - `SESSION_STATE.AddonsEvidence.<addon_key>`
     - `SESSION_STATE.RepoFacts.CapabilityEvidence`
     - `SESSION_STATE.Diagnostics.ReasonPayloads`
5. phase integration section (minimum: Phase 2/2.1/4/5/6 expectations)
   - phase semantics MUST reference canonical `master.md` phase labels and MUST NOT redefine them locally
6. evidence contract section (SESSION_STATE paths, status/warning handling)
7. Examples (GOOD/BAD)
8. Troubleshooting with at least 3 concrete symptom->cause->fix entries
9. shared principal-governance delegation block:
    - `## Shared Principal Governance Contracts (Binding)`
    - `rules.principal-excellence.md`
    - `rules.risk-tiering.md`
    - `rules.scorecard-calibration.md`
    - loaded-addon tracking keys under `SESSION_STATE.LoadedRulebooks.addons.*`
    - tracking keys are audit/trace pointers (map entries), not activation signals

Exception for shared contract rulebooks themselves:
- If `profile_key` is one of `principal-excellence`, `risk-tiering`, `scorecard-calibration`,
  generate the corresponding canonical shared contract section directly instead of delegation.

Claims without evidence mapping MUST be marked `not-verified`.

Taxonomy rule (binding):
- Profile rulebooks define profile behavior.
- Addon activation remains manifest-owned (`profiles/addons/*.addon.yml`) and MUST NOT be embedded as profile-selection logic.
- `applicability_signals` are descriptive for audit/explain outputs and MUST NOT be used as profile-selection activation logic by themselves.

---

## Shared Principal Governance Contracts (Binding)

Every generated non-shared profile MUST include a delegation section that references:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

And MUST include tracking keys:

- `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
- `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
- `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`

Tracking semantics (binding):
- `SESSION_STATE.LoadedRulebooks.addons` is a map (`addon_key -> path`) used for loaded-rulebook traceability.
- These keys document loaded shared contracts and MUST NOT be interpreted as independent activation logic.

---

## Output Files (Binding)

This command MUST produce:

- Preferred: `profiles/rules_<profile_key>.md`
- Accepted legacy alias: `profiles/rules.<profile_key>.md`

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
