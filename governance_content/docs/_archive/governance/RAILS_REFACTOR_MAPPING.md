# Rails Refactor Mapping (Old -> New)

## Rule -> Canonical Location

| rule_id | rule_summary | canonical_source | secondary_references |
|---|---|---|---|
| R001 | Start-mode semantics are binary (Cold vs Warm) | `master.md` (2.4.1) | `rules.md` (7.3.3), `start.md` output requirements |
| R002 | Runtime routing/transition/gate decisions are kernel-owned | `governance/kernel/*` + `governance/phase_api.yaml` | `docs/governance/RESPONSIBILITY_BOUNDARY.md` |
| R003 | Session-state field contract is schema-owned | `governance/assets/schemas/session_state.core.v1.schema.json` | `SESSION_STATE_SCHEMA.md` |
| R004 | MD rails are non-binding AI guidance | `docs/governance/RESPONSIBILITY_BOUNDARY.md` | `master.md`, `rules.md`, `start.md`, `README-RULES.md` |
| R005 | Profile optional state target semantics (`null` target; legacy placeholders documented only) | `SESSION_STATE_SCHEMA.md` | `master.md` MIN template examples |

## Content Migration (old -> new)

| original_section | target_location | action |
|---|---|---|
| Start-mode mixed phrase in core rails | `master.md` 2.4.1 / `rules.md` 7.3.3 / `start.md` output bullets | removed + reduced |
| Monolithic operational guidance in central rails | `docs/governance/rails/*.md` | moved |
| Repeated boundary wording across docs | `docs/governance/RESPONSIBILITY_BOUNDARY.md` | merged |
| Runtime-like guidance snippets in central rails | kernel/schema references from central rails | reduced |

## File Classification (required + conditional)

| file | classification | note |
|---|---|---|
| `master.md` | central-core | global principles + references only |
| `rules.md` | central-core | technical policy + presentation rails |
| `start.md` | central-core | start-facing guidance, kernel references |
| `SESSION_STATE_SCHEMA.md` | schema-adjacent-doc | data contract documentation |
| `continue.md` | guidance-only | no runtime authority |
| `docs/_archive/resume.md` | guidance-only | resume behavior guidance only |
| `docs/_archive/resume_prompt.md` | guidance-only | controlled resume prompt template |
| `README-RULES.md` | descriptive-map | non-normative authority map |
