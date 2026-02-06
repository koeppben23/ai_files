# OpenAPI Contracts Addon Rulebook (v1.0)

This document defines the **OpenAPI contracts** addon rules.
It is applied **in addition** to the Core Rulebook (`rules.md`), the Master Prompt (`master.md`), and any active profile.

Priority order on conflict:
`master.md` > `rules.md` (Core) > active profile > this addon.

---

## 0. Core principle (binding)

> The OpenAPI spec is the source of truth for externally visible REST behavior.

If an OpenAPI spec exists, the assistant MUST treat it as authoritative for:
- Paths, methods, request/response schemas, required/optional fields
- Error responses (status codes, payload shape) when specified
- Security schemes and required auth headers when specified

If the spec is ambiguous or incomplete, the assistant MUST say so explicitly and propose a safe default.

---

## 1. Discovery & authority selection (binding)

When this addon is required, the assistant MUST:

1) Identify the spec roots (repo-driven). Examples:
   - `openapi.yaml|yml|json`, `swagger.yaml|yml|json`
   - generated or bundled specs (e.g., `apis/**` or `src/main/resources/**`)
2) Record spec evidence in `SESSION_STATE.AddonsEvidence.openapi.signals`.
3) Select the **authoritative spec set** (single file or a directory) and record it in `SESSION_STATE.Scope.ExternalAPIs` or `SESSION_STATE.RepoMapDigest`.

Conflict rule:
- If multiple specs exist and overlap on the same operationId/path, the assistant MUST surface the conflict and ask the operator to choose the authoritative one (or use repo convention if deterministic).

---

## 2. Change rules (binding)

### 2.1 Contract-first workflow

If the ticket changes externally visible REST behavior, the assistant MUST plan changes in this order:
1) Update OpenAPI spec (or reference the intended spec change if owned elsewhere)
2) Regenerate stubs/clients (only if the repo uses generators)
3) Implement server-side behavior
4) Validate with tests

If the ticket changes only internal behavior (no contract change), the assistant MUST explicitly state that the OpenAPI contract remains unchanged and ensure no accidental contract drift.

### 2.2 Backward compatibility

Unless the ticket explicitly requests a breaking change, the assistant MUST preserve backward compatibility:
- No removing endpoints or fields
- No tightening required constraints
- No changing field types in a non-accepting way
- Prefer additive changes: new optional fields, new endpoints, new enum values with safe defaults

If a breaking change is unavoidable, the assistant MUST:
- call it out explicitly
- propose a versioning strategy (new path version, new endpoint, or content negotiation)

---

## 3. Server implementation alignment (binding)

The assistant MUST ensure:
- Request validation matches schema constraints (required, min/max, formats) where applicable
- Response serialization matches field naming and nullability expectations
- Status codes match what the spec declares

If the repo uses Springdoc/Swagger annotations, the assistant MUST keep annotations consistent with the spec.

---

## 4. Tests (binding)

When the OpenAPI contract is touched (directly or effectively), tests MUST include at least one of:
- controller tests verifying request/response shapes and status codes
- integration tests against the running app (e.g., SpringBootTest)

Tests MUST cover:
- happy path for at least one operation
- one representative error path (validation or not-found or unauthorized), aligned with spec if specified

---

## 5. Evidence (binding)

Any statement about “contract matches” MUST be supported by evidence:
- build/test output references in `SESSION_STATE.BuildEvidence` (or the repo’s actual evidence block)
- or explicit diff review of spec + implementation if automated checks are absent

If no automated contract check exists, the assistant MUST recommend adding one (non-blocking recommendation).
