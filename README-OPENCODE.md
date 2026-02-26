# OpenCode Governance Guide

This file describes OpenCode runtime usage and operational recovery.
It is non-normative guidance.

## Source of Truth

- System routing, execution, and validation: `${COMMANDS_HOME}/phase_api.yaml` via `governance/kernel/*`
- Technical and quality constraints: `rules.md` + active profile/addon rulebooks
- Session-state schema and invariants: `SESSION_STATE_SCHEMA.md`

## Quick Links

- Root product overview: `README.md`
- Bootstrap guide: `BOOTSTRAP.md`
- Runtime phase spec: `${COMMANDS_HOME}/phase_api.yaml`
- Core technical constraints: `rules.md`
- Rules structure map: `README-RULES.md`
- Install layout/path model: `docs/install-layout.md`

## Audience

For operators and developers running governed sessions in OpenCode who need reliable bootstrap, persistence, and recovery behavior.

## OpenCode Lifecycle

- Bootstrap: Use local launcher (`~/.config/opencode/bin/opencode-governance-bootstrap`)
- `/continue`: execute the next deterministic step from session state
- `/resume`: continue an interrupted session deterministically
- `/audit`: read-only governance report flow

See `BOOTSTRAP.md` for detailed bootstrap instructions.

## Bootstrap and Binding Evidence

Canonical OpenCode bootstrap uses installer-owned binding evidence:

- `<config_root>/commands/governance.paths.json`

If binding evidence is unavailable or unresolved, bootstrap must fail closed (for example with binding/path reason codes).
Preflight records only raw tool availability (BuildToolchain snapshot); repo-specific build mapping happens later in Phase 2.

## Support Matrix

- Supported host OS: macOS, Linux, Windows (canonical path model from binding evidence + kernel loaders, layout examples in `docs/install-layout.md`).
- Required tools for standard operation: `${PYTHON_COMMAND}` (installer/helpers), `git` (identity-gated workflows).
- Supported command lifecycle: `/continue`, `/resume`, `/audit`.

## Session State and Persistence

Runtime persistence is repo-scoped under `${WORKSPACES_HOME}/<repo_fingerprint>/...` with a global active pointer at `${SESSION_STATE_POINTER_FILE}`.

Operational helpers:

```bash
python governance/entrypoints/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>
python governance/entrypoints/persist_workspace_artifacts.py --repo-root <repo_path>
python scripts/migrate_session_state.py --workspace <repo_fingerprint>
```

Use `--dry-run` when validating changes before writing.

## 60-Second OpenCode Verification

```bash
${PYTHON_COMMAND} install.py --status
${PYTHON_COMMAND} governance/entrypoints/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --dry-run
```

Then run the local bootstrap launcher and confirm bootstrap succeeds without binding/identity blockers.

Response rendering quick check:

```bash
${PYTHON_COMMAND} scripts/render_response_envelope.py --input response.json --format markdown
${PYTHON_COMMAND} scripts/render_response_envelope.py --input response.json --format plain
${PYTHON_COMMAND} scripts/render_response_envelope.py --input response.json --format json
```

`--format auto` is the default and resolves to plain for interactive TTY sessions (stable across Windows/macOS/Linux terminals) and JSON for non-interactive execution.

## Profiles and Addons

Profiles and addons are loaded from `profiles/` with deterministic precedence from kernel policy resolution.

- Profile rulebooks: `profiles/rules*.md`
- Addon manifests: `profiles/addons/*.addon.yml`

Factory generation entrypoints:

- `new_profile.md`
- `new_addon.md`

Conformance reference for generated artifacts:

- `governance/PROFILE_ADDON_FACTORY_CONTRACT.json`

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

- Runtime behavior is governed by `${COMMANDS_HOME}/phase_api.yaml` and `governance/kernel/*`.
- OpenCode behavior described here is subordinate to kernel/spec semantics and `rules.md` constraints.

## Related Docs

- Install and path layout: `docs/install-layout.md`
- Phases and gate map: `docs/phases.md`
- Release flow: `docs/releasing.md`
- Security gates: `docs/security-gates.md`
- Customer bundle: `docs/customer-install-bundle-v1.md`
