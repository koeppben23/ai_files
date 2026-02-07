# Docs Governance Addon

Purpose (binding): keep governance markdown and addon manifests consistent, reviewable, and machine-checkable without introducing hard delivery blockers.

Addon class (binding): advisory addon.

Non-blocking policy (binding): this addon MUST NOT set BLOCKED by itself. Drift/lint findings are surfaced as WARN status codes plus concrete recovery actions.

---

## Scope

This addon applies to governance-oriented documentation and manifests in the active repository scope, especially:
- `master.md`
- `SESSION_STATE_SCHEMA.md`
- `rules.md`
- `profiles/rules.*.md`
- `profiles/addons/*.addon.yml`
- `README*.md`

Activation signals are manifest-owned (`profiles/addons/docsGovernance.addon.yml`).

---

## Phase Integration

### Phase 1 (scan/context)
SHOULD:
- collect in-scope governance docs/manifests
- record addon evidence status

### Phase 2 / 2.1 (plan/decision)
MUST:
- provide a short Docs Drift Summary covering:
  - master <-> schema consistency
  - README <-> master terminology/link consistency
  - manifest <-> rulebook reference consistency

### Phase 4 (implementation)
MUST:
- keep docs edits small and auditable
- keep terms and field paths consistent with canonical sources

### Phase 5/6 (verification/final QA)
MUST:
- run available doc-governance checks (tests/scripts)
- if checks cannot run, emit warning status + recovery plan

---

## Evidence Contract

When active, this addon SHOULD maintain:
- `SESSION_STATE.AddonsEvidence.docsGovernance.signals` (array)
- `SESSION_STATE.AddonsEvidence.docsGovernance.required` (bool)
- `SESSION_STATE.AddonsEvidence.docsGovernance.status` (`loaded|skipped|missing-rulebook`)

Docs drift result (recommended object):

```yaml
SESSION_STATE:
  AddonsEvidence:
    docsGovernance:
      status: loaded
      checks:
        schemaMaster: pass | warn
        readmeMaster: pass | warn
        manifestRulebook: pass | warn
      warnings:
        - code: WARN-DOCS-README-DRIFT
          message: "README path example does not match canonical install layout"
          recovery: "Align README example with installer outputs"
```

Gate review scorecard for docs checks (recommended):

```yaml
SESSION_STATE:
  AddonsEvidence:
    docsGovernance:
      scorecard:
        Score: 7
        MaxScore: 9
        Criteria:
          - id: DOC-SCHEMA-MASTER-CONSISTENCY
            weight: 3
            critical: true
            result: pass | fail | partial | not-applicable
            evidenceRef: EV-001
          - id: DOC-MANIFEST-RULEBOOK-CONSISTENCY
            weight: 3
            critical: true
            result: pass | fail | partial | not-applicable
            evidenceRef: EV-002
          - id: DOC-README-CANONICAL-TERMS
            weight: 3
            critical: false
            result: pass | fail | partial | not-applicable
            evidenceRef: EV-003
```

Binding:
- If a docs-governance criterion marked `critical=true` is `fail`, status MUST include a WARN code and recovery plan.
- Docs-governance scorecard MUST NOT directly set `Mode=BLOCKED` (advisory addon).

Claim-to-evidence (binding):
- Any PR-critical docs claim (e.g., "schema aligned", "manifest references valid", "README terms canonical") MUST map to an `evidenceRef`.
- If evidence is missing, claim MUST be marked `not-verified`.

---

## Status Codes and Recovery

- `WARN-DOCS-SCHEMA-DRIFT`
  - Meaning: master references session fields not represented in schema (or conflicting enums/semantics)
  - Recovery: align `SESSION_STATE_SCHEMA.md` and `master.md` in same change

- `WARN-DOCS-MANIFEST-RULEBOOK-MISSING`
  - Meaning: manifest points to missing rulebook, or docs reference non-existent rulebook
  - Recovery: add missing file or fix reference

- `WARN-DOCS-README-DRIFT`
  - Meaning: README terminology/paths conflict with canonical governance docs
  - Recovery: normalize README wording/paths to master/schema

---

## Conventions (Binding)

MUST:
- keep primary terms stable:
  - Primary Profile -> `SESSION_STATE.ActiveProfile` (singular)
  - Templates -> `SESSION_STATE.LoadedRulebooks.templates`
  - Addons -> `SESSION_STATE.LoadedRulebooks.addons.<addon_key>`
  - Addon evidence -> `SESSION_STATE.AddonsEvidence.<addon_key>`
- keep activation logic in manifest files; rulebooks describe behavior, not detection signals
- prefer explicit file references in docs over vague prose

MUST NOT:
- redefine normative behavior in README documents that conflicts with `master.md` / `rules.md`
- mix profile and addon terminology ambiguously

Canonical terms lint (binding):
- Avoid deprecated/confusing aliases in governance docs. Prefer canonical forms:
  - `rules.frontend-angular-nx.md` (not `rules.frontend.md`)
  - `BLOCKED-MISSING-TEMPLATES` (do not use legacy templates-missing variant)
  - `BLOCKED-MISSING-ADDON:<addon_key>` (not ad-hoc addon-specific BLOCKED names)

---

## Cross-file Consistency Matrix (Binding)

When docs are touched in this scope, maintain a compact matrix:

```yaml
DocsConsistencyMatrix:
  master_schema: pass | warn
  readme_master: pass | warn
  manifests_rulebooks: pass | warn
  profile_addon_terms: pass | warn
```

Binding:
- Any `warn` entry MUST include status code + recovery action.
- Matrix results SHOULD be linked to evidence IDs.

---

## Tooling / CI Guidance

Recommended checks:
- `python3 scripts/validate_addons.py --repo-root <repo>`
- `pytest -q -m governance`

If checks are unavailable in environment, output explicit not-verified status and recovery commands.

---

## Examples (GOOD/BAD)

GOOD:
- `profiles/addons/foo.addon.yml` references existing `rulebook: rules.foo.md`.

BAD:
- README states a path/field that contradicts `master.md` canonical paths.

GOOD:
- Drift warning emitted with status code + concrete recovery step.

BAD:
- Blocking entire workflow for a docs-only drift that can be fixed in follow-up.

---

## Troubleshooting

1) Symptom: docs mention addon not loaded
- Cause: manifest missing or signal too narrow
- Fix: add/fix addon manifest and rerun docs checks

2) Symptom: schema/master mismatch warnings keep recurring
- Cause: state field changed in one file only
- Fix: update both files in one commit and add governance test guard

3) Symptom: README confusion around profile vs addon
- Cause: terminology drift
- Fix: normalize README wording to canonical terms above

---

## Output Requirement (Agent)

When this addon is active and docs were changed, include a "Docs Governance Summary" with this template:

```text
Docs Governance Summary
- Changed docs: <list>
- Checks executed: <commands/tests>
- DocsConsistencyMatrix: <pass/warn entries>
- Open WARN codes: <code -> recovery>
- Claim-to-evidence map: <claim -> EV-xxx | not-verified>
```

Reviewability requirement (binding):
- Summary MUST be concise and reviewer-ready (auditable without re-reading all docs).

END OF ADDON

---

## Principal Excellence Contract (Binding)

This rulebook is considered principal-grade only when the contract below is satisfied.

### Gate Review Scorecard (binding)

When this rulebook is active and touches changed scope, the workflow MUST maintain a scorecard entry with weighted criteria, critical flags, and evidence references.

```yaml
SESSION_STATE:
  GateScorecards:
    principal_excellence:
      Score: 0
      MaxScore: 0
      Criteria:
        - id: PRINCIPAL-QUALITY-CLAIMS-EVIDENCED
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-001 | not-verified
        - id: PRINCIPAL-DETERMINISM-AND-TEST-RIGOR
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-002 | not-verified
        - id: PRINCIPAL-ROLLBACK-OR-RECOVERY-READY
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-003 | not-verified
```

### Claim-to-evidence (binding)

Any non-trivial claim (for example: contract-safe, tests green, architecture clean, deterministic) MUST map to an `evidenceRef`.
If evidence is missing, the claim MUST be marked `not-verified`.

### Exit criteria (binding)

- All criteria with `critical: true` MUST be `pass` before declaring principal-grade completion.
- Advisory add-ons MUST remain non-blocking, but MUST emit WARN status code + recovery when critical criteria are not pass.
- Required templates/add-ons MAY block code-phase according to master/core/profile policy when critical criteria cannot be satisfied safely.

### Recovery when evidence is missing (binding)

Emit a warning code plus concrete recovery commands/steps and keep completion status as `not-verified`.
Recommended code: `WARN-PRINCIPAL-EVIDENCE-MISSING`.

---

## Principal Hardening v2.1 - Standard Risk Tiering (Binding)

### RTN-1 Canonical tiers (binding)

All addon/template assessments MUST use this canonical tier syntax:

- `TIER-LOW`: local/internal changes with low blast radius and no external contract or persistence risk.
- `TIER-MEDIUM`: behavior changes with user-facing, API-facing, or multi-module impact.
- `TIER-HIGH`: contract, persistence/migration, messaging/async, security, or rollback-sensitive changes.

If uncertain, choose the higher tier.

### RTN-2 Tier evidence minimums (binding)

- `TIER-LOW`: build/lint (if present) + targeted changed-scope tests.
- `TIER-MEDIUM`: `TIER-LOW` evidence + at least one negative-path assertion for changed behavior.
- `TIER-HIGH`: `TIER-MEDIUM` evidence + one deterministic resilience/rollback-oriented proof (retry/idempotency/recovery/concurrency as applicable).

### RTN-3 Tier-based gate decisions (binding)

- A gate result cannot be `pass` when mandatory tier evidence is missing.
- For advisory addons, missing tier evidence remains non-blocking but MUST emit WARN + recovery and result `partial` or `fail`.
- For required addons/templates, missing `TIER-HIGH` evidence MAY block code-phase per master/core/profile policy.

### RTN-4 Required SESSION_STATE shape (binding)

```yaml
SESSION_STATE:
  RiskTiering:
    ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
    Rationale: "short evidence-based reason"
    MandatoryEvidence:
      - EV-001
      - EV-002
    MissingEvidence: []
```

### RTN-5 Unresolved tier handling (binding)

If tier cannot be determined from available evidence, set status code `WARN-RISK-TIER-UNRESOLVED`, provide a conservative default (`TIER-HIGH`), and include recovery steps to refine classification.

---

## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)

### CAL-1 Standard criterion weights by tier (binding)

For principal scorecards in addon/template rulebooks, criteria weights MUST use this standard model:

- `TIER-LOW`: each active criterion weight = `2`
- `TIER-MEDIUM`: each active criterion weight = `3`
- `TIER-HIGH`: each active criterion weight = `5`

No custom weights are allowed unless explicitly documented as repo-specific exception with rationale and risk note.

### CAL-2 Critical-flag normalization (binding)

The following criteria classes MUST be marked `critical: true` when applicable:

- contract/integration correctness
- determinism and anti-flakiness
- rollback/recovery safety
- security semantics and authorization behavior

Non-critical criteria MAY exist, but cannot compensate for a failed critical criterion.

### CAL-3 Tier score thresholds (binding)

A principal-grade gate result MAY be `pass` only if all conditions are true:

- all applicable critical criteria are `pass`
- total score ratio meets threshold:
  - `TIER-LOW`: >= `0.80`
  - `TIER-MEDIUM`: >= `0.85`
  - `TIER-HIGH`: >= `0.90`

If threshold is missed, result MUST be `partial` or `fail` with recovery actions.

### CAL-4 Cross-addon comparability (binding)

When multiple addons are active in one ticket, scorecards MUST be directly comparable by using:

- canonical tier labels (`TIER-LOW|MEDIUM|HIGH`)
- standardized weight model from CAL-1
- identical pass thresholds from CAL-3

### CAL-5 Required SESSION_STATE calibration evidence (binding)

```yaml
SESSION_STATE:
  GateScorecards:
    principal_excellence:
      ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
      Score: 0
      MaxScore: 0
      ScoreRatio: 0.00
      Threshold: 0.80 | 0.85 | 0.90
      CalibrationVersion: v2.1.1
```

### CAL-6 Calibration warning code (binding)

If scorecard data is incomplete or non-comparable, emit `WARN-SCORECARD-CALIBRATION-INCOMPLETE` and block principal-grade declaration (`not-verified`).

