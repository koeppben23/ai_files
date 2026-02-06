# Frontend OpenAPI TypeScript Client Addon

Addon class (binding): advisory addon.

Purpose: align frontend API usage with OpenAPI-driven TypeScript client generation when present.

Non-blocking policy: if generator setup is unclear, emit WARN + recovery steps and keep behavior conservative.

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

END OF ADDON
