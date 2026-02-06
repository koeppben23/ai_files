# OpenAPI Contracts Addon Rulebook (v1.1)

This document defines the **OpenAPI contracts** addon rules.
It is applied **in addition** to the Core Rulebook (`rules.md`), the Master Prompt (`master.md`), and any active profile.

Priority order on conflict:
`master.md` > `rules.md` (Core) > active profile > this addon.

**Non-blocking policy (binding):** This addon MUST NOT hard-block delivery. If critical prerequisites are missing (spec root unclear, version unknown, no contract checks), the assistant MUST surface a **status code** (Section 8), record it in `SESSION_STATE.AddonsEvidence.openapi.status`, provide **recovery steps**, and proceed with conservative, repo-driven defaults.

**Separation of concerns (binding):** Activation signals belong in the addon manifest (`profiles/addons/openapi.addon.yml`). This rulebook defines behavior once the addon is active.

---

## 0. Core principle (binding)

> The OpenAPI spec is the source of truth for externally visible REST behavior.

If an OpenAPI spec exists, the assistant MUST treat it as authoritative for:
- paths/methods, request/response schemas, required vs optional fields
- error responses (status codes, payload shape) when specified
- security schemes and required headers when specified

If the spec is ambiguous or incomplete, the assistant MUST say so explicitly and propose a safe default.

---

## 1. Phase integration (binding)

This addon integrates with the governance phases defined by `master.md`:

- **Phase 1.4–1.5 (Addon activation & planning):**
  - Confirm spec roots + authoritative spec set (Section 3).
  - Infer spec version & tooling (Section 2).
  - Produce a contract-driven implementation plan (Section 5) and record key decisions.

- **Phase 2 (Repository discovery):**
  - Collect evidence signals in `SESSION_STATE.AddonsEvidence.openapi.signals`.
  - Record any high-risk status codes (Section 8) and the chosen recovery action.

- **Phase 4 (Implementation):**
  - Implement changes to match the contract and keep server annotations/config aligned (Section 6).

- **Phase 5.3 (Quality gate):**
  - Run repo-native contract checks if available (Section 7).
  - If mismatch is detected, surface `WARN-OPENAPI-SPEC-IMPLEMENTATION-MISMATCH` and propose concrete diffs/remediations.

---

## 2. Version & capability inference (binding)

When this addon is required, the assistant MUST attempt to infer:

1) **OpenAPI version** (`2.0` vs `3.0.x` vs `3.1.x`) directly from the spec header:
   - `openapi: 3.0.3` or `openapi: 3.1.0`
   - `swagger: "2.0"`

2) **Repo-native contract tooling** already present (CI workflows, scripts, Maven/Gradle plugins). Examples:
   - `openspec` / `spectral` / `swagger-cli`
   - breaking-change detection (e.g. `oasdiff`)
   - generator usage (e.g. `openapi-generator`)

The assistant MUST record inference evidence in:
- `SESSION_STATE.AddonsEvidence.openapi.signals`

If the version cannot be inferred, set status `WARN-OPENAPI-VERSION-UNKNOWN` and proceed assuming **OpenAPI 3.0** semantics (more conservative and widely supported).

**Version-aware rules (binding):**
- **OpenAPI 3.1:** full JSON Schema 2020-12; prefer `type: [T, "null"]` over `nullable`; prefer `examples` over `example`.
- **OpenAPI 3.0:** JSON Schema subset; `nullable: true` is valid/expected in many repos.
- **OpenAPI 2.0:** different top-level structure (`swagger: "2.0"`); no `components` section.

---

## 3. Discovery & authority selection (binding)

When this addon is active, the assistant MUST:

1) Identify spec roots (repo-driven). Common locations:
   - `openapi.yaml|yml|json`, `swagger.yaml|yml|json`
   - `apis/**`, `openspec/**`, `src/main/resources/**`

2) Record spec evidence in `SESSION_STATE.AddonsEvidence.openapi.signals`.

3) Select the **authoritative spec set** (single file or directory) and record it in `SESSION_STATE.Scope.ExternalAPIs` (preferred) or `SESSION_STATE.RepoMapDigest`.

Conflict rule:
- If multiple specs overlap on the same path+method (or operationId), the assistant MUST surface the conflict and propose a deterministic selection strategy (repo convention). If no deterministic rule exists, the assistant MUST ask the operator to choose the authoritative spec.

---

## 4. Structural linting & hygiene (binding)

The assistant MUST prefer **structural** checks over ad-hoc grep:
- Parse/validate the spec (YAML/JSON) with repo-native tooling if present.
- If tooling is absent, perform a careful structural review of the touched sections and recommend adding linting (non-blocking).

Minimum hygiene when editing specs:
- Keep component names consistent and stable.
- Avoid copy/paste schema drift; reuse components.
- Provide at least one example for new operations or new response bodies (version-appropriate: `example` vs `examples`).

---

## 5. Change rules (binding)

### 5.1 Contract-first workflow

If the ticket changes externally visible REST behavior, the assistant MUST plan changes in this order:
1) Update OpenAPI spec (or reference the intended spec change if owned elsewhere)
2) Regenerate stubs/clients **only if** the repo uses generators
3) Implement server-side behavior
4) Validate with tests and (if available) contract checks

If the ticket changes only internal behavior (no contract change), the assistant MUST explicitly state that the OpenAPI contract remains unchanged and guard against accidental contract drift.

### 5.2 Backward compatibility

Unless the ticket explicitly requests a breaking change, the assistant MUST preserve backward compatibility:
- no removing endpoints or fields
- no tightening required constraints
- no changing field types in a non-accepting way
- prefer additive changes: new optional fields, new endpoints, new enum values with safe defaults

If a breaking change is unavoidable, the assistant MUST:
- call it out explicitly
- propose a versioning strategy (new path version, new endpoint, or content negotiation)
- record status `WARN-OPENAPI-BREAKING-CHANGE-UNAPPROVED` unless explicit approval is present

---

## 6. Server implementation alignment (binding)

The assistant MUST ensure:
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

**CI/CD (binding):** If the repo already contains a contract check (workflow, script, Maven/Gradle task), the assistant MUST use it and cite it as evidence.

**If no automated contract check exists:** the assistant MUST recommend adding one (non-blocking). Prefer:
- spec linting (Spectral or equivalent)
- breaking-change detection (oasdiff or equivalent)

---

## 8. Status codes & recovery (binding)

These status codes replace hard blocking. They MUST be:
- written to `SESSION_STATE.AddonsEvidence.openapi.status`
- shown in the plan/summary with a concrete recovery action

### WARN-OPENAPI-VERSION-UNKNOWN

**Trigger:** Spec version cannot be inferred from `openapi:` or `swagger:` fields.

**Recovery steps:**
1) Locate authoritative spec(s) and confirm the header.
2) If needed, introduce a small repo config (e.g. `.openapi-config.yaml`) stating version and spec root.

---

### WARN-OPENAPI-MISSING-SPEC

**Trigger:** Addon is required but no spec is found in expected locations.

**Recovery steps:**
1) Confirm whether the service is externally exposed.
2) If yes: create the spec or declare its location.
3) If no: set `SESSION_STATE.Scope.ExternalAPIs = []` and explain why the addon was considered.

---

### WARN-OPENAPI-SPEC-IMPLEMENTATION-MISMATCH

**Trigger:** Evidence indicates implementation diverges from spec (tests/CI, manual diff review, or generation checks).

**Recovery steps:**
1) Identify mismatch class (status code, field naming, missing fields, schema type mismatch).
2) Decide direction: fix implementation vs update spec (only with explicit contract change intent).
3) Re-run repo-native contract checks (or add a minimal one if absent).

---

### WARN-OPENAPI-BREAKING-CHANGE-UNAPPROVED

**Trigger:** A breaking change is introduced without explicit approval.

**Recovery steps:**
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
