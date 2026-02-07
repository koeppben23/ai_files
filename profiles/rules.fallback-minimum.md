# Fallback Minimum Profile

Purpose:
Provide a mandatory baseline when a target repository lacks explicit
standards (no CI, no test conventions, no documented build steps).

## Activation condition
This profile applies ONLY when no repo-local standards are discoverable.

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
