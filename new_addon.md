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
- `signals.any` with at least one signal item

The `rulebook` value MUST resolve to an existing profile rulebook path after generation.

---

## Rulebook Contract (Binding)

Generated addon rulebook MUST include:

1. addon class declaration (`required` or `advisory`)
2. activation/blocking semantics consistent with addon class
3. domain-specific hardening section for changed scope
4. principal baseline sections:
   - `## Principal Excellence Contract (Binding)`
   - `## Principal Hardening v2.1 - Standard Risk Tiering (Binding)`
   - `## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)`

For advisory addons, non-blocking behavior MUST still emit WARN + recovery when critical evidence is missing.

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
- canonical risk tiers exist (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`)
- calibration thresholds exist (`0.80`, `0.85`, `0.90`)
- warning codes exist:
  - `WARN-PRINCIPAL-EVIDENCE-MISSING`
  - `WARN-SCORECARD-CALIBRATION-INCOMPLETE`

If checklist fails, status MUST be `not-verified`.

---

## Suggested Conventional Commit

- `feat(governance): add <addon_key> principal addon and manifest`
