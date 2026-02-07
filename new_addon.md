# Governance Factory - New Addon

Purpose (binding):
- Create a new addon as a conformance pair:
  - addon rulebook `profiles/rules.<addon-rulebook>.md`
  - addon manifest `profiles/addons/<addon_key>.addon.yml`

The pair MUST be principal-grade at creation time.

---

## Required Input (Binding)

Provide all fields:

- `addon_key`: manifest key (filename stem)
- `addon_class`: `required` or `advisory`
- `rulebook_name`: target rulebook filename stem
- `signals`: deterministic activation signals
- `domain_scope`: what behavior this addon governs
- `critical_quality_claims`: top claims requiring evidence

If any required field is absent, return `BLOCKED` with missing field list.

---

## Manifest Contract (Binding)

Generated manifest MUST include:

- `addon_key`
- `addon_class`
- `rulebook`
- `manifest_version` (currently `1`)
- `path_roots` (relative repo paths; use `.` when repo-wide)
- `signals.any` with at least one signal item

The `rulebook` value MUST resolve to an existing profile rulebook path after generation.

---

## Rulebook Contract (Binding)

Generated addon rulebook MUST include:

1. canonical precedence reference to `rules.md` Section 4.6 (do not redefine local precedence order)
2. addon class declaration (`required` or `advisory`)
3. activation semantics (manifest-owned) + blocking behavior consistent with addon class
4. phase integration section (minimum: Phase 2/2.1/4/5.3/6 expectations)
5. evidence contract section (SESSION_STATE paths, lifecycle status, WARN handling)
6. domain-specific hardening section for changed scope
7. Examples (GOOD/BAD)
8. Troubleshooting with at least 3 concrete symptom->cause->fix entries
9. shared principal-governance delegation block:
   - `## Shared Principal Governance Contracts (Binding)`
   - `rules.principal-excellence.md`
   - `rules.risk-tiering.md`
   - `rules.scorecard-calibration.md`
   - loaded-addon tracking keys under `SESSION_STATE.LoadedRulebooks.addons.*`

Exception for shared contract addons:
- If creating one of the canonical shared addons (`principalExcellence`, `riskTiering`, `scorecardCalibration`),
  the target rulebook itself defines the corresponding shared contract section directly.

For advisory addons, non-blocking behavior MUST still emit WARN + recovery when critical evidence is missing.

Canonical addon semantics (binding):
- Addon class behavior is defined by core/master policy and MUST be referenced, not redefined.
- `required`: missing rulebook at code-phase maps to `BLOCKED-MISSING-ADDON:<addon_key>`.
- `advisory`: continue non-blocking with WARN + recovery.

---

## Shared Principal Governance Contracts (Binding)

Every generated non-shared addon rulebook MUST include delegation references to:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

And tracking keys:

- `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
- `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
- `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`

---

## Output Files (Binding)

This command MUST produce:

- `profiles/addons/<addon_key>.addon.yml`
- `profiles/rules.<rulebook_name>.md`

Optional:

- update to `CHANGELOG.md` `[Unreleased]` when requested.

---

## Principal Conformance Checklist (Binding)

Before finalizing, verify:

- manifest and rulebook are name/path-consistent
- addon class semantics are explicit and coherent
- shared contract delegation block references all three shared governance rulebooks
- loaded-addon tracking keys exist:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- warning codes exist:
  - `WARN-PRINCIPAL-EVIDENCE-MISSING`
  - `WARN-SCORECARD-CALIBRATION-INCOMPLETE`

For shared contract addons themselves:
- ensure canonical tiering/calibration/scorecard contract sections are present in the shared rulebook.

If checklist fails, status MUST be `not-verified`.

---

## Suggested Conventional Commit

- `feat(governance): add <addon_key> principal addon and manifest`
