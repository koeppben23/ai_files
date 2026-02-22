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
- `owns_surfaces` (non-empty)
- `touches_surfaces` (non-empty)

Capability-first alignment (binding):
- At least one capability field MUST be present: `capabilities_any` or `capabilities_all`.
- Prefer explicit capability declarations so activation is capability-first with hard-signal fallback.

The `rulebook` value MUST resolve to an existing profile rulebook path after generation.

---

## Quality Contract (Binding)

Every addon MUST define quality enforcement rules:

### Required Output Sections (User Mode)

When `addon_class = required` in user mode, the addon MUST enforce these output sections for all implementation tasks:

1. **Intent & Scope** - What is being built and why
2. **Non-goals** - What is explicitly out of scope
3. **Design/Architecture** - Structural decisions with rationale
4. **Invariants & Failure Modes** - What must always/never happen
5. **Test Plan (Matrix)** - Coverage strategy by test type
6. **Edge Cases Checklist** - Boundary conditions and corner cases
7. **Verification Commands** - Exact commands for human execution
8. **Risk Review** - NPE/leaks/concurrency/security analysis
9. **Rollback Plan** - How to undo if deployment fails

### Verification Handshake (Binding)

In user mode, verified status requires explicit human confirmation:

```
LLM Output: "Verification Commands: [cmd1, cmd2, ...]"
Human Response: "Executed [cmd1]: [result1]; Executed [cmd2]: [result2]"
LLM: Set `Verified` only after receiving results; otherwise mark `NOT_VERIFIED`
```

### Risk-Tier Triggers (Binding)

When touched files match risk surfaces, addon MUST require:

| Risk Surface | Additional Requirements |
|--------------|------------------------|
| Persistence/Pointer | NPE audit, Leak audit, Rollback plan |
| Security/Auth | Threat model checklist, Input validation audit |
| Concurrency | Thread-safety audit, Race condition checklist |
| External APIs | Contract tests, Timeout handling, Retry logic |

### Claim Verification (Binding)

- No silent assumptions: Every assumption marked `ASSUMPTION`
- No unverified claims: Everything not executed marked `NOT_VERIFIED`
- Language/Version: Explicit choice with rationale (no guessing)

---

## Rulebook Contract (Binding)

Generated addon rulebook MUST include:

1. canonical precedence reference to `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` (do not redefine local precedence order)
2. addon class declaration (`required` or `advisory`)
3. activation semantics (manifest-owned) + blocking behavior consistent with addon class
4. phase integration section (minimum: Phase 2/2.1/4/5.3/6 expectations)
   - phase semantics MUST reference canonical `master.md` phase labels and MUST NOT redefine them locally
5. evidence contract section (canonical SESSION_STATE paths, lifecycle status, WARN handling)
   - include explicit paths used by runtime diagnostics/contracts:
     - `SESSION_STATE.AddonsEvidence.<addon_key>`
     - `SESSION_STATE.RepoFacts.CapabilityEvidence`
     - `SESSION_STATE.Diagnostics.ReasonPayloads`
6. domain-specific hardening section for changed scope
7. quality contract section (required output sections, verification handshake, risk-tier triggers)
8. Examples (GOOD/BAD)
9. Troubleshooting with at least 3 concrete symptom->cause->fix entries
10. shared principal-governance delegation block:
    - `## Shared Principal Governance Contracts (Binding)`
    - `rules.principal-excellence.md`
    - `rules.risk-tiering.md`
    - `rules.scorecard-calibration.md`
    - loaded-addon tracking keys under `SESSION_STATE.LoadedRulebooks.addons.*`
    - tracking keys are audit/trace pointers (map entries), not activation signals

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

Tracking semantics (binding):
- `SESSION_STATE.LoadedRulebooks.addons` is a map (`addon_key -> path`) used for loaded-rulebook traceability.
- These keys document loaded shared contracts and MUST NOT be interpreted as independent activation logic.

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
- quality contract section includes:
  - required output sections (9 items)
  - verification handshake semantics
  - risk-tier trigger table

For shared contract addons themselves:
- ensure canonical tiering/calibration/scorecard contract sections are present in the shared rulebook.

If checklist fails, status MUST be `not-verified`.

---

## Suggested Conventional Commit

- `feat(governance): add <addon_key> principal addon and manifest`
