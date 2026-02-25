# Rails Refactor Mapping (Old -> New)

## Goal

Reduce duplicated runtime language in central markdown rails and keep canonical ownership explicit.

## Canonical Mapping

| Rule Topic | Canonical Location | Secondary References |
|---|---|---|
| Start-mode banner semantics | `master.md` section 2.4.1 | `rules.md`, `start.md` (non-binding references) |
| Runtime transition/routing semantics | `governance/kernel/*` + `governance/phase_api.yaml` | `docs/governance/RESPONSIBILITY_BOUNDARY.md` |
| Session-state data contract | `governance/assets/schemas/session_state.core.v1.schema.json` | `SESSION_STATE_SCHEMA.md` |
| Bootstrap/default state payload shape | `governance/application/use_cases/bootstrap_persistence.py` | `governance/entrypoints/session_state_contract.py`, `bootstrap/session_state_contract.py` |

## Thematic Rails Split

Operational guidance moved to thematic rails under `docs/governance/rails/`:

- `planning.md`
- `implementation.md`
- `testing.md`
- `pr_review.md`
- `failure_handling.md`

These files are guidance-only and do not define runtime routing authority.
