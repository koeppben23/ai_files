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
  - `BLOCKED-MISSING-TEMPLATES` (not `BLOCKED-TEMPLATES-MISSING`)
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
