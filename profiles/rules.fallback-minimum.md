# Fallback Minimum Profile Rulebook (v1.0)

## Intent (binding)

Provide a mandatory baseline when a target repository lacks explicit standards (no CI, no test conventions, no documented build steps).

## Scope (binding)

Applies to repos where no deterministic stack profile can be selected and minimum safe build/test/docs governance is required.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This fallback profile applies only when no stack profile can be selected deterministically.
It is applied in addition to `master.md` (phases, gates, activation) and `rules.md` (core engineering governance).

## Activation condition
This profile applies ONLY when no repo-local standards are discoverable.

## Phase integration (binding)

- Phase 2: document missing standards and the minimum runnable baseline proposal.
- Phase 2.1: include explicit decision for minimal verification path (unit/integration/smoke).
- Phase 4: implement the smallest safe baseline for build/test/docs in changed scope.
- Phase 5/6: verify executed evidence or mark `not-verified` with copy/paste recovery commands.

## Evidence contract (binding)

When fallback is active, maintain:
- `SESSION_STATE.BuildEvidence` entries for every verification claim.
- `SESSION_STATE.RiskTiering` rationale or explicit fallback rationale when canonical tiering data is unavailable.
- `warnings[]` with recovery actions when checks cannot be executed in the current environment.

If evidence is missing, claims MUST be marked `not-verified` and completion MUST remain non-final.

## Mandatory baseline (MUST)
- Identify how to build and verify the project.
  If not present, propose and establish a minimal runnable baseline.
- Do not claim verification without executed checks or explicit justification.
- For non-trivial changes, introduce or recommend minimal automation (CI).

## Minimum verification (MUST)
At least one of:
- Unit tests for core logic changes
- Integration test for boundary changes when feasible
- Smoke verification (build + basic run) if tests are absent

## Minimal tooling commands (recommended)

Use repo-native commands when available; otherwise propose minimal equivalents:
- Python: `${PYTHON_COMMAND} -m pytest -q`
- Node: `npm test`
- Maven: `mvn -q test`
- Gradle: `./gradlew test`
- Build smoke: repo-native build command + one startup/check command

## Documentation (MUST)
- Ensure build/test instructions exist (create minimal documentation if missing).
- Record non-trivial decisions in ADR.md or an equivalent mechanism.

## Quality heuristics (SHOULD)
- Deterministic behavior; no hidden mutable state.
- Coherent error handling; no silent failures.
- Logging at critical boundaries without leaking sensitive data.

## Portability (MUST when persisting)
Use platform-neutral storage locations as defined in rules.md.

---
## Principal Hardening v2 - Fallback Minimum Safety (Binding)

### FMPH2-1 Baseline scorecard criteria (binding)

When fallback profile is active, the scorecard MUST evaluate and evidence:

- `FALLBACK-BUILD-VERIFY-EXECUTED`
- `FALLBACK-MINIMUM-TEST-COVERAGE`
- `FALLBACK-DOCS-UPDATED`
- `FALLBACK-RISK-NOTED`
- `FALLBACK-ROLLBACK-OR-RECOVERY-PLAN`

Each criterion MUST include an `evidenceRef`.

### FMPH2-2 Minimum acceptance matrix (binding)

Fallback completion requires evidence for at least one of:

- unit tests for changed business logic
- integration or boundary test for changed interfaces
- smoke build/run verification when tests are unavailable

Additionally, one representative negative-path check MUST be present for changed behavior.

### FMPH2-3 Hard fail criteria (binding)

Gate result MUST be `fail` if any applies:

- no executed verification evidence exists
- changed behavior has no test or smoke verification path
- no recovery/rollback guidance is documented for non-trivial changes
- decisions are made without recorded rationale in docs/ADR equivalent

### FMPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps:

- `WARN-FALLBACK-BASELINE-UNKNOWN`
- `WARN-FALLBACK-TESTING-INSUFFICIENT`
- `WARN-FALLBACK-RECOVERY-UNSPECIFIED`

## Examples (GOOD/BAD)

GOOD:
- Unknown repo receives a minimal deterministic verification plan (build + targeted test or smoke check) with explicit evidence capture.

BAD:
- Declaring completion without any executable verification or recovery guidance.

## Troubleshooting

1) Symptom: No runnable test tool is available
- Cause: repo has no test harness or missing dependencies in host
- Fix: document `not-verified`, provide minimal bootstrap command, and run smoke validation.

2) Symptom: Build command unclear in legacy repository
- Cause: missing docs/CI conventions
- Fix: infer from repo files, record assumption, and provide conservative fallback commands.

3) Symptom: Gate cannot pass due missing evidence
- Cause: claims made without BuildEvidence links
- Fix: execute minimal checks and map each claim to explicit evidence refs.

---

## Shared Principal Governance Contracts (Binding)

This rulebook uses shared advisory governance contracts:

- `rules.principal-excellence.md`
- `rules.risk-tiering.md`
- `rules.scorecard-calibration.md`

Binding behavior:

- When this rulebook is active in execution/review phases, load these as advisory governance contracts.
- Record when loaded:
  - `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
  - `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
  - `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`
- If one of these shared rulebooks is unavailable, emit WARN + recovery, mark affected claims as
  `not-verified`, and continue conservatively.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# End of file — rules.fallback-minimum.md
