# Rules Overview

This document is a non-normative map of the governance rule structure.
It does not define independent behavior. On conflict, follow `master.md`, then `rules.md`, then active profile/addon rulebooks.

## Source of Truth

- Workflow phases, gates, path variables, precedence, and fail-closed runtime semantics: `master.md`
- Core technical and quality constraints: `rules.md`
- Release readiness Go/No-Go contract: `STABILITY_SLA.md`
- Session-state contract: `SESSION_STATE_SCHEMA.md`

## Rule Layers

- Core governance and lifecycle control: `master.md`
- Core stack-agnostic engineering constraints: `rules.md`
- Stack/domain extensions: `profiles/rules*.md`
- Optional or required addon policies: manifests in `profiles/addons/*.addon.yml` with rulebooks in `profiles/`

Profiles and addons must not weaken core fail-closed obligations.

## Current System Baseline

- Deterministic engine/runtime behavior is implemented in `governance/engine/` and response projection in `governance/render/`.
- Claim verification is fail-closed (`NOT_VERIFIED-MISSING-EVIDENCE`, `NOT_VERIFIED-EVIDENCE-STALE`).
- Session-state rollout is in engine-first posture with canonical schema enforcement.
- Mode-aware repo-doc constraints, precedence events, and prompt budgets are active and documented in `docs/mode-aware-repo-rules.md`.

## Rulebook Selection and Discovery

- Explicit profile selection is preferred.
- If no explicit profile exists, deterministic repo-signal detection is used.
- If profile ambiguity materially affects tooling or gate decisions, workflow must block until clarified.

See `rules.md` for binding profile selection and ambiguity handling details.

## Operational References

- OpenCode usage and recovery: `README-OPENCODE.md`
- Conflict handling model: `CONFLICT_RESOLUTION.md`
- Quality index and cross-references: `QUALITY_INDEX.md`
- Phases map: `docs/phases.md`

## License

See `LICENSE`.
