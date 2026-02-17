# OpenCode Governance Guide

This file describes OpenCode runtime usage and operational recovery.
It is non-normative. If anything here conflicts with `master.md` or `rules.md`, follow `master.md` and `rules.md`.

## Authority and Scope

- System phases, gates, path variables, and fail-closed behavior: `master.md`
- Technical and quality constraints: `rules.md`
- Session-state schema and invariants: `SESSION_STATE_SCHEMA.md`
- Frontend mirror for Codex-like surfaces: `AGENTS.md` (non-normative)

## OpenCode Lifecycle

- `/start`: mandatory bootstrap entrypoint for OpenCode sessions
- `/continue`: execute the next deterministic step from session state
- `/resume`: continue an interrupted session deterministically
- `/audit`: read-only diagnostics report flow

`/start` is responsible for binding evidence, command preflight, and bootstrap checks before deeper workflow execution.

## Bootstrap and Binding Evidence

Canonical OpenCode bootstrap uses installer-owned binding evidence:

- `<config_root>/commands/governance.paths.json`

If binding evidence is unavailable or unresolved, bootstrap must fail closed (for example with binding/path reason codes).

## Session State and Persistence

Runtime persistence is repo-scoped under `${WORKSPACES_HOME}/<repo_fingerprint>/...` with a global active pointer at `${SESSION_STATE_POINTER_FILE}`.

Operational helpers:

```bash
python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>
python diagnostics/persist_workspace_artifacts.py --repo-root <repo_path>
python scripts/migrate_session_state.py --workspace <repo_fingerprint>
```

Use `--dry-run` when validating changes before writing.

## Profiles and Addons

Profiles and addons are loaded from `profiles/` with deterministic precedence from `master.md`.

- Profile rulebooks: `profiles/rules*.md`
- Addon manifests: `profiles/addons/*.addon.yml`

Factory generation entrypoints:

- `new_profile.md`
- `new_addon.md`

Conformance reference for generated artifacts:

- `diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json`

## Runtime and Evidence Notes

- Claim verification remains fail-closed: missing evidence and stale evidence are surfaced as `NOT_VERIFIED` reason codes.
- Mode-aware repo-doc constraints and prompt budgets are documented in `docs/mode-aware-repo-rules.md`.
- Runtime engine and render implementation live in `governance/engine/` and `governance/render/`.

## Related Docs

- Install and path layout: `docs/install-layout.md`
- Phases and gate map: `docs/phases.md`
- Release flow: `docs/releasing.md`
- Security gates: `docs/security-gates.md`
- Customer bundle: `docs/customer-install-bundle-v1.md`
