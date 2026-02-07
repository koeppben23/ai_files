# Frontend OpenAPI TypeScript Client Addon

Addon class (binding): advisory addon.

## Intent (binding)

Align frontend API usage with OpenAPI-driven TypeScript client generation when present.

## Scope (binding)

Frontend API client generation, DTO-to-UI mapping boundaries, and contract-oriented frontend evidence quality.

Non-blocking policy: if generator setup is unclear, emit WARN + recovery steps and keep behavior conservative.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This advisory addon refines API-client behavior and MUST NOT override `master.md`, `rules.md`, or active profile constraints.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/frontendOpenApiTsClient.addon.yml`.
This rulebook defines behavior once activated; it MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 2: record activation signals and generator/spec evidence in `SESSION_STATE.AddonsEvidence.frontendOpenApiTsClient.signals`.
- Phase 2.1: decide authoritative generator/spec roots and record recovery if unresolved.
- Phase 4: regenerate client via repo-native command; avoid hand edits in generated output.
- Phase 5.3: verify changed API-facing behavior with at least one negative-path assertion.

## Evidence contract (binding)

When active, maintain:
- `SESSION_STATE.AddonsEvidence.frontendOpenApiTsClient.required`
- `SESSION_STATE.AddonsEvidence.frontendOpenApiTsClient.signals`
- `SESSION_STATE.AddonsEvidence.frontendOpenApiTsClient.status` (`loaded|skipped|missing-rulebook`)
- warning codes in `warnings[]` for advisory drift/unknown tooling.

## Binding guidance

- If repo already has API client generation scripts/config, use them; do not hand-edit generated output.
- Keep mapping from generated DTOs to UI models explicit.
- For changed API-facing behavior, include at least one negative-path test (error contract path).

## Suggested warnings

- `WARN-FE-OPENAPI-GENERATOR-UNKNOWN`
- `WARN-FE-OPENAPI-DRIFT-RISK`
- `WARN-FE-OPENAPI-NO-NEGATIVE-TEST`

## Recovery steps template

1. Locate generator command/config in repo scripts or CI.
2. Regenerate client deterministically.
3. Add/update contract-aligned frontend tests.

## Tooling (recommended)

Repo-native command hints:
- Generator script: `npm run generate:api` (if defined by repo)
- Nx target variant: `npx nx run <project>:generate-api` (if configured)
- Validation fallback: repo OpenAPI validation command before frontend tests

## Examples (GOOD/BAD)

GOOD:
- Generated client updated only via generator command; UI mapping changes remain in non-generated files.

BAD:
- Hand-editing files under generated client output to bypass a spec mismatch.

## Troubleshooting

1) Symptom: generated client changed but app compile fails
- Cause: mapping layer still expects old DTO shape
- Fix: update explicit mapper/adapters and re-run tests.

2) Symptom: unclear spec root in monorepo
- Cause: multiple `openapi*` files with no ownership convention
- Fix: choose authoritative spec root in Decision Pack and record evidence.

## Principal Hardening v2 - Frontend OpenAPI TS Client (Binding)

### FOPH2-1 Required scorecard criteria (binding)

When API-client scope is touched, the scorecard MUST evaluate and evidence:

- `FE-OPENAPI-GENERATOR-TRACEABLE`
- `FE-OPENAPI-NO-HAND-EDIT-GENERATED`
- `FE-OPENAPI-MODEL-MAPPING-EXPLICIT`
- `FE-OPENAPI-CONTRACT-NEGATIVE-TEST`
- `FE-OPENAPI-DRIFT-CHECK-RESULT`

Each criterion MUST include an `evidenceRef`.

### FOPH2-2 Required implementation workflow (binding)

For API-facing changes, workflow order MUST be:

1. confirm authoritative spec/generator command
2. regenerate client deterministically
3. implement mapping/adaptation in non-generated code
4. execute contract-aligned frontend tests (happy + error path)

### FOPH2-3 Hard fail criteria (binding)

Gate result MUST be `fail` if any applies:

- generated client output changed by manual edits
- changed API usage without explicit DTO-to-UI mapping
- changed API-facing behavior without negative-path contract assertion
- generator/spec source remains unknown and no conservative recovery plan is recorded

### FOPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps when advisory handling remains non-blocking:

- `WARN-FE-OPENAPI-SOURCE-UNRESOLVED`
- `WARN-FE-OPENAPI-MAPPING-DRIFT-RISK`
- `WARN-FE-OPENAPI-CONTRACT-TEST-MISSING`

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
