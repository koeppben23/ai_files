# OpenAPI Contracts Addon Rulebook (v1.1)

This document defines the **OpenAPI contracts** addon rules.
It is applied **in addition** to the Core Rulebook (`rules.md`), the Master Prompt (`master.md`), and any active profile.

## Intent (binding)

Treat OpenAPI artifacts as authoritative contract surfaces and keep implementation changes contract-consistent and evidence-backed.

## Scope (binding)

OpenAPI spec authority, version/tool inference, contract drift detection, and contract-aligned implementation evidence.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
This addon refines OpenAPI-specific behavior after activation and MUST NOT override master/core/profile constraints.

## Activation (binding)

Addon class: `advisory`.

Non-blocking policy (binding): This addon MUST NOT hard-block delivery. If critical prerequisites are missing (spec root unclear, version unknown, no contract checks), the workflow MUST surface a status code (Section 8), record it in `SESSION_STATE.AddonsEvidence.openapi.status`, provide recovery steps, and proceed with conservative, repo-driven defaults.

Separation of concerns (binding): Activation signals belong in the addon manifest (`profiles/addons/openapi.addon.yml`). This rulebook defines behavior once the addon is active.

## Evidence contract (binding)

When active, maintain:
- `SESSION_STATE.AddonsEvidence.openapi.required`
- `SESSION_STATE.AddonsEvidence.openapi.signals`
- `SESSION_STATE.AddonsEvidence.openapi.status` (`loaded|skipped|missing-rulebook` or WARN status codes)
- mismatch diff evidence entries when contract drift is detected.

## Tooling (recommended)

SHOULD use repo-native contract tooling first (Spectral/swagger-cli/oasdiff/generator checks). If unavailable, use conservative structural validation and emit recovery commands.

---

## 0. Core principle (binding)

> The OpenAPI spec is the source of truth for externally visible REST behavior.

If an OpenAPI spec exists, the workflow MUST treat it as authoritative for:
- paths/methods, request/response schemas, required vs optional fields
- error responses (status codes, payload shape) when specified
- security schemes and required headers when specified

If the spec is ambiguous or incomplete, the workflow MUST say so explicitly and propose a safe default.

---

## 1. Phase integration (binding)

This addon integrates with the governance phases defined by `master.md`:

- **Phase 2 (Repository discovery):**
  - Collect evidence signals in `SESSION_STATE.AddonsEvidence.openapi.signals`.
  - Record any high-risk status codes (Section 8) and the chosen recovery action.

- **Phase 2.1 (Decision Pack):**
  - Confirm spec roots + authoritative spec set (Section 3).
  - Infer spec version & tooling (Section 2).
  - Produce a contract-driven implementation plan (Section 5) and record key decisions.

- **Phase 4 (Implementation):**
  - Implement changes to match the contract and keep server annotations/config aligned (Section 6).

- **Phase 5.3 (Quality gate):**
  - Run repo-native contract checks if available (Section 7).
  - If mismatch is detected, surface `WARN-OPENAPI-SPEC-IMPLEMENTATION-MISMATCH` and propose concrete diffs/remediations.

### 1.1 Mismatch evidence template (binding)

When mismatch is detected, record compact diff evidence in session state:

```yaml
SESSION_STATE:
  AddonsEvidence:
    openapi:
      status: WARN-OPENAPI-SPEC-IMPLEMENTATION-MISMATCH
      diffEvidence:
        - path: "<spec path>"
          operation: "<METHOD /path or operationId>"
          expected: "<contract excerpt>"
          observed: "<implementation/test excerpt>"
          recovery: "<minimal corrective action>"
```

---

## 2. Version & capability inference (binding)

When this addon is required, the workflow MUST attempt to infer:

1) **OpenAPI version** (`2.0` vs `3.0.x` vs `3.1.x`) directly from the spec header:
   - `openapi: 3.0.3` or `openapi: 3.1.0`
   - `swagger: "2.0"`

2) **Repo-native contract tooling** already present (CI workflows, scripts, Maven/Gradle plugins). Examples:
   - `openspec` / `spectral` / `swagger-cli`
   - breaking-change detection (e.g. `oasdiff`)
   - generator usage (e.g. `openapi-generator`)

The workflow MUST record inference evidence in:
- `SESSION_STATE.AddonsEvidence.openapi.signals`

If the version cannot be inferred, set status `WARN-OPENAPI-VERSION-UNKNOWN` and proceed assuming **OpenAPI 3.0** semantics (more conservative and widely supported).

**Version-aware rules (binding):**
- **OpenAPI 3.1:** full JSON Schema 2020-12; prefer `type: [T, "null"]` over `nullable`; prefer `examples` over `example`.
- **OpenAPI 3.0:** JSON Schema subset; `nullable: true` is valid/expected in many repos.
- **OpenAPI 2.0:** different top-level structure (`swagger: "2.0"`); no `components` section.

---

## 3. Discovery & authority selection (binding)

When this addon is active, the workflow MUST:

1) Identify spec roots (repo-driven). Common locations:
   - `openapi.yaml|yml|json`, `swagger.yaml|yml|json`
   - `apis/**`, `openspec/**`, `src/main/resources/**`

2) Record spec evidence in `SESSION_STATE.AddonsEvidence.openapi.signals`.

3) Select the **authoritative spec set** (single file or directory) and record it in `SESSION_STATE.Scope.ExternalAPIs` (preferred) or `SESSION_STATE.RepoMapDigest`.

Conflict rule:
- If multiple specs overlap on the same path+method (or operationId), the workflow MUST surface the conflict and propose a deterministic selection strategy (repo convention). If no deterministic rule exists, the workflow MUST ask the operator to choose the authoritative spec.

---

## 4. Structural linting & hygiene (binding)

The workflow MUST prefer **structural** checks over ad-hoc grep:
- Parse/validate the spec (YAML/JSON) with repo-native tooling if present.
- If tooling is absent, perform a careful structural review of the touched sections and recommend adding linting (non-blocking).

Minimum hygiene when editing specs:
- Keep component names consistent and stable.
- Avoid copy/paste schema drift; reuse components.
- Provide at least one example for new operations or new response bodies (version-appropriate: `example` vs `examples`).

### 4.1 Quick tooling commands (recommended)

If the repo does not already provide a contract/lint command, the assistant SHOULD propose one of the following **copy/paste** options (choose what fits the repo tooling):

**Option A: Spectral (Node)**
```bash
# one-time: add tooling (repo decides whether to commit package-lock)
npm i -D @stoplight/spectral-cli
npx spectral lint openapi.yaml
```

**Option B: swagger-cli validate (Node)**
```bash
npm i -D swagger-cli
npx swagger-cli validate openapi.yaml
```

**Option C: Python structural check (minimal example)**
```python
# lint_openapi_minimal.py (example)
import sys, json
from pathlib import Path

p = Path(sys.argv[1])
raw = p.read_text(encoding="utf-8")

# Minimal JSON-only structural check. If your repo uses YAML, prefer repo-native tooling.
if not raw.lstrip().startswith("{"):
    print("WARN: minimal linter example only supports JSON; use repo-native YAML tooling.", file=sys.stderr)
    sys.exit(0)

doc = json.loads(raw)

if "openapi" not in doc and doc.get("swagger") != "2.0":
    raise SystemExit("ERROR: missing 'openapi' (3.x) or 'swagger: 2.0' header")

paths = doc.get("paths") or {}
if not isinstance(paths, dict) or not paths:
    raise SystemExit("ERROR: no paths found")

print("OK: basic OpenAPI structure present")
```

---

## 5. Change rules (binding)

### 5.1 Contract-first workflow

If the ticket changes externally visible REST behavior, the workflow MUST plan changes in this order:
1) Update OpenAPI spec (or reference the intended spec change if owned elsewhere)
2) Regenerate stubs/clients **only if** the repo uses generators
3) Implement server-side behavior
4) Validate with tests and (if available) contract checks

If the ticket changes only internal behavior (no contract change), the workflow MUST explicitly state that the OpenAPI contract remains unchanged and guard against accidental contract drift.

### 5.2 Backward compatibility

Unless the ticket explicitly requests a breaking change, the workflow MUST preserve backward compatibility:
- no removing endpoints or fields
- no tightening required constraints
- no changing field types in a non-accepting way
- SHOULD use additive changes: new optional fields, new endpoints, new enum values with safe defaults

If a breaking change is unavoidable, the workflow MUST:
- call it out explicitly
- propose a versioning strategy (new path version, new endpoint, or content negotiation)
- record status `WARN-OPENAPI-BREAKING-CHANGE-UNAPPROVED` unless explicit approval is present

---

## 6. Server implementation alignment (binding)

The workflow MUST ensure:
- request validation matches schema constraints (required, min/max, formats) where applicable
- response serialization matches field naming and nullability expectations
- status codes match what the spec declares

If the repo uses Springdoc/Swagger annotations:
- keep annotations consistent with the spec
- never “paper over” a mismatch by only changing annotations; either spec or behavior must be updated

---

## 7. Tests & CI/CD integration (binding)

When the OpenAPI contract is touched (directly or effectively), tests MUST include at least one of:
- controller tests verifying request/response shapes and status codes
- integration tests against the running app (e.g., SpringBootTest)

Tests MUST cover:
- one happy path for at least one operation
- one representative error path (validation, not-found, unauthorized), aligned with spec if specified

**CI/CD (binding):** If the repo already contains a contract check (workflow, script, Maven/Gradle task), the workflow MUST use it and cite it as evidence.

**If no automated contract check exists:** the workflow MUST recommend adding one (non-blocking). Prefer:
- spec linting (Spectral or equivalent)
- breaking-change detection (oasdiff or equivalent)

### 7.1 Suggested commands (copy/paste)

Pick the lightest option that matches repo constraints.

**Spectral lint**
```bash
npx spectral lint <spec-file-or-glob>
```

**Breaking-change detection with oasdiff**
```bash
# Compare "base" vs "revision" (paths can be local files or URLs)
oasdiff breaking <base-spec> <revision-spec>
```

**openapi-generator validate (if generator is already used)**
```bash
openapi-generator validate -i <spec-file>
```

### 7.2 Example GitHub Actions job (reference)

If the repo uses GitHub Actions but has no contract job yet, propose a minimal job like:

```yaml
name: openapi-contract
on:
  pull_request:
jobs:
  openapi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm i -D @stoplight/spectral-cli
      - run: npx spectral lint apis/**/*.y*ml
```

---

## 8. Status codes & recovery (binding)

These status codes replace hard blocking. They MUST be:
- written to `SESSION_STATE.AddonsEvidence.openapi.status`
- shown in the plan/summary with a concrete recovery action

### WARN-OPENAPI-VERSION-UNKNOWN

**Condition:** Spec version cannot be inferred from `openapi:` or `swagger:` fields.

**Operator guidance:**
1) Locate authoritative spec(s) and confirm the header.
2) If needed, introduce a small repo config (e.g. `.openapi-config.yaml`) stating version and spec root.

---

### WARN-OPENAPI-MISSING-SPEC

**Condition:** Addon is required but no spec is found in expected locations.

**Operator guidance:**
1) Confirm whether the service is externally exposed.
2) If yes: create the spec or declare its location.
3) If no: set `SESSION_STATE.Scope.ExternalAPIs = []` and explain why the addon was considered.

---

### WARN-OPENAPI-SPEC-IMPLEMENTATION-MISMATCH

**Condition:** Evidence indicates implementation diverges from spec (tests/CI, manual diff review, or generation checks).

**Operator guidance:**
1) Identify mismatch class (status code, field naming, missing fields, schema type mismatch).
2) Decide direction: fix implementation vs update spec (only with explicit contract change intent).
3) Re-run repo-native contract checks (or add a minimal one if absent).

---

### WARN-OPENAPI-BREAKING-CHANGE-UNAPPROVED

**Condition:** A breaking change is introduced without explicit approval.

**Operator guidance:**
1) Revert to additive change, OR
2) Implement a versioning strategy, OR
3) Capture explicit approval and document migration path.

---

## 9. Examples (non-exhaustive)

### 9.1 Additive change (preferred)
- Add optional field `middleName` to a response schema.
- Update implementation to serialize it (nullable/optional), update tests.

### 9.2 Breaking change (must be explicit)
- Rename `personId` to `id` in response.
- Requires explicit approval + versioning plan; otherwise status `WARN-OPENAPI-BREAKING-CHANGE-UNAPPROVED`.

### 9.3 Error contract alignment
- Spec declares `401` with `{ code, message }`.
- Ensure your exception handler returns that shape; cover with at least one integration/controller test.

### 9.4 GOOD/BAD examples

**GOOD (additive, backward compatible):**
- Add new optional field with clear semantics and an example.
- Keep existing fields untouched.

```yaml
components:
  schemas:
    Person:
      type: object
      required: [personId]
      properties:
        personId:
          type: string
        middleName:
          type: string
          nullable: true
          example: "Alex"
```

**BAD (silent breaking change):**
- Make an existing field required or change its type without versioning.

```yaml
# BAD: personId was string, now integer (breaks clients)
personId:
  type: integer
```

---

## 10. Troubleshooting (non-blocking)

Use this section when a contract workflow is unclear.

### Symptom: Multiple OpenAPI specs, unclear which is authoritative
- **Likely cause:** monorepo/submodules or legacy specs.
- **Action:** choose a deterministic authority rule (directory root, service name mapping, or CI workflow target) and record it in `SESSION_STATE.Scope.ExternalAPIs`. If still unclear, emit `WARN-OPENAPI-MISSING-SPEC` (or a custom warn-code) and ask the operator to pick.

### Symptom: Contract check fails in CI but local changes seem correct
- **Likely cause:** CI uses a different spec root/glob, or compares against a baseline spec.
- **Action:** locate the CI job/script, mirror the same command locally, and update either (a) spec, (b) implementation, or (c) baseline reference with explicit intent.

### Symptom: Spec declares response fields that are missing in JSON
- **Likely cause:** serialization config, mapping layer, or nullability mismatch.
- **Action:** verify DTO mapping and Jackson configuration; add controller/integration test covering the missing field; decide whether spec or implementation is wrong and correct with explicit contract intent.

### Symptom: Breaking-change detection flags changes you think are additive
- **Likely cause:** required-array changed, enum narrowed, or response code removed.
- **Action:** ensure changes are additive: only add optional fields, add enum values (not remove), add response codes (not remove). If breaking change is intended, document versioning/migration.

---

## Principal Hardening v2 - OpenAPI Contract Quality (Binding)

### OAPH2-1 Required scorecard criteria (binding)

When OpenAPI contract scope is touched, the scorecard MUST evaluate and evidence:

- `OPENAPI-SPEC-AUTHORITY-IDENTIFIED`
- `OPENAPI-BACKWARD-COMPAT-VERIFIED`
- `OPENAPI-IMPLEMENTATION-ALIGNED`
- `OPENAPI-CONTRACT-CHECK-EVIDENCE`
- `OPENAPI-ERROR-PATH-PROOF`

Each criterion MUST include an `evidenceRef`.

### OAPH2-2 Required verification workflow (binding)

For changed contract scope, evidence MUST include at least:

- one spec validation pass (linting or structural check)
- one happy-path controller/integration test aligned to spec
- one error-path test aligned to spec error responses

If a row is not applicable, explicit rationale is required.

### OAPH2-3 Hard fail criteria (binding)

Gate result MUST be `fail` if any applies:

- no authoritative spec identified for changed contract scope
- breaking change introduced without explicit approval
- implementation diverges from spec with no mismatch evidence recorded
- no contract check evidence for changed API behavior

### OAPH2-4 Warning codes and recovery (binding)

Use status codes below with concrete recovery steps when advisory handling remains non-blocking:

- `WARN-OPENAPI-VERSION-UNKNOWN`
- `WARN-OPENAPI-MISSING-SPEC`
- `WARN-OPENAPI-SPEC-IMPLEMENTATION-MISMATCH`
- `WARN-OPENAPI-BREAKING-CHANGE-UNAPPROVED`

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
