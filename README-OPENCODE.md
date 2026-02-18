# OpenCode Governance Guide

This file describes OpenCode runtime usage and operational recovery.
It is non-normative. If anything here conflicts with `master.md` or `rules.md`, follow `master.md` and `rules.md`.

## Source of Truth

- System phases, gates, path variables, and fail-closed behavior: `master.md`
- Technical and quality constraints: `rules.md`
- Session-state schema and invariants: `SESSION_STATE_SCHEMA.md`
- Frontend mirror for Codex-like surfaces: `AGENTS.md` (non-normative)

## Quick Links

- Root product overview: `README.md`
- Core runtime contract: `master.md`
- Core technical constraints: `rules.md`
- Rules structure map: `README-RULES.md`
- Install layout/path model: `docs/install-layout.md`

## Audience

For operators and developers running governed sessions in OpenCode who need reliable bootstrap, persistence, and recovery behavior.

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

## Support Matrix

- Supported host OS: macOS, Linux, Windows (canonical path model in `master.md`, layout examples in `docs/install-layout.md`).
- Required tools for standard operation: `${PYTHON_COMMAND}` (installer/helpers), `git` (identity-gated workflows).
- Supported command lifecycle: `/start`, `/continue`, `/resume`, `/audit`.

## Session State and Persistence

Runtime persistence is repo-scoped under `${WORKSPACES_HOME}/<repo_fingerprint>/...` with a global active pointer at `${SESSION_STATE_POINTER_FILE}`.

Operational helpers:

```bash
python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>
python diagnostics/persist_workspace_artifacts.py --repo-root <repo_path>
python scripts/migrate_session_state.py --workspace <repo_fingerprint>
```

Use `--dry-run` when validating changes before writing.

## 60-Second OpenCode Verification

```bash
${PYTHON_COMMAND} install.py --status
${PYTHON_COMMAND} diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --dry-run
```

Then run `/start` in OpenCode and confirm bootstrap succeeds without binding/identity blockers.

Response rendering quick check:

```bash
${PYTHON_COMMAND} scripts/render_response_envelope.py --input response.json --format markdown
${PYTHON_COMMAND} scripts/render_response_envelope.py --input response.json --format plain
${PYTHON_COMMAND} scripts/render_response_envelope.py --input response.json --format json
```

`--format auto` is the default and resolves to plain for interactive TTY sessions (stable across Windows/macOS/Linux terminals) and JSON for non-interactive execution.

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

## Troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun `${PYTHON_COMMAND} install.py`, then verify with `${PYTHON_COMMAND} install.py --status`.
- `BLOCKED-VARIABLE-RESOLUTION`: validate config-root/path binding resolution (`docs/install-layout.md`).
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure current directory is a git repo and `git` is available in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE` or `NOT_VERIFIED-EVIDENCE-STALE`: refresh/provide evidence and rerun.

## Version and Compatibility

- Runtime contract version is defined by the `Governance-Version` header in `master.md`.
- OpenCode behavior described here is subordinate to `master.md`, `rules.md`, and active profile/addon rulebooks.

## Related Docs

- Install and path layout: `docs/install-layout.md`
- Phases and gate map: `docs/phases.md`
- Release flow: `docs/releasing.md`
- Security gates: `docs/security-gates.md`
- Customer bundle: `docs/customer-install-bundle-v1.md`
