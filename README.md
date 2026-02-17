# Governance and Prompt System

Deterministic governance for AI-assisted software delivery with fail-closed gates, evidence requirements, and reproducible session state.

Normative precedence:
- `master.md` is the system source of truth for phases, gates, path variables, and fail-closed behavior.
- `rules.md` defines core technical and quality constraints.
- Active profile and addon rulebooks in `profiles/` extend stack-specific behavior.
- `AGENTS.md` is a non-normative frontend mirror; on conflict, `master.md` wins.

Definition: in this repository, "normative" means `master.md`, `rules.md`, and active profile/addon rulebooks; "non-normative surfaces" means `README*` files and `AGENTS.md`.

## Start Here

- OpenCode bootstrap entrypoint: `start.md`
- OpenCode operational guide: `README-OPENCODE.md`
- Rules structure overview: `README-RULES.md`
- Stability/release contract: `STABILITY_SLA.md`
- Canonical session-state schema: `SESSION_STATE_SCHEMA.md`

## What This Repository Provides

- Deterministic phase workflow (`1` through `6`) with explicit gate outcomes.
- Repo-aware governance runtime under `governance/` with tested fail-closed semantics.
- Installer and customer handoff flow (`install.py`, release/bundle docs).
- Diagnostics and schema contracts under `diagnostics/`.
- Profile and addon ecosystem under `profiles/`.

## Quick Start

- Install locally: `python3 install.py`
- Run deterministic dry-run first: `python3 install.py --dry-run`
- In OpenCode, start a governed session with `/start`
- Continue an active session with `/continue` or `/resume`

Note: installer-owned path binding evidence is written to `<config_root>/commands/governance.paths.json` and is required for canonical OpenCode bootstrap behavior.

## Support Matrix

- Operating systems: macOS, Linux, Windows (path resolution is defined in `master.md` and installation layout examples in `docs/install-layout.md`).
- Runtime requirements: `python3` for installer/diagnostics helpers; `git` is recommended and required by identity-gated workflows.
- Frontend surfaces: OpenCode (`/start`, `/continue`, `/resume`, `/audit`) and Codex-style frontend surfaces via `AGENTS.md` mirror semantics.

## 60-Second Install Verification

Run the following after checkout or after installation:

```bash
python3 install.py --dry-run
python3 install.py
python3 install.py --status
```

Expected outcome:

- `--dry-run` reports planned actions without writes.
- install run completes without blocker reason codes.
- `--status` reports installed governance assets and healthy path bindings.

Then, in OpenCode, run `/start` and confirm bootstrap succeeds without binding/path blockers.

## Troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun `python3 install.py`, then verify with `python3 install.py --status`.
- `BLOCKED-VARIABLE-RESOLUTION`: check resolved config root/path bindings against `docs/install-layout.md`.
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure repository is a git checkout and `git` is available in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE`: provide missing evidence artifacts and rerun the gate.
- `NOT_VERIFIED-EVIDENCE-STALE`: refresh evidence (new probe/measurement) and rerun.

Deep security and diagnostics references are in `docs/security-gates.md` and `docs/phases.md`.

## Version and Compatibility

- This README tracks the current repository baseline; the authoritative runtime contract version is the `Governance-Version` header in `master.md`.
- For release readiness and compatibility gates, always apply `STABILITY_SLA.md` and the release process in `docs/releasing.md`.

## Runtime State and Paths

Canonical variables and resolution are defined in `master.md`.

- Global active session pointer: `${SESSION_STATE_POINTER_FILE}`
- Repo-scoped workspace/session artifacts: `${WORKSPACES_HOME}/<repo_fingerprint>/...`
- Runtime error logs: `${WORKSPACES_HOME}/<repo_fingerprint>/logs/` (fallback `${CONFIG_ROOT}/logs/`)

See `docs/install-layout.md` for full layout details.

## Documentation Map

- Lifecycle and gates: `docs/phases.md`
- Install layout and path model: `docs/install-layout.md`
- Release process: `docs/releasing.md`
- Release security model: `docs/release-security-model.md`
- Security gates and scanner policy: `docs/security-gates.md`
- Mode-aware repo-doc and host-permission orchestration: `docs/mode-aware-repo-rules.md`
- Customer bundle contract: `docs/customer-install-bundle-v1.md`
- Benchmarks and quality run guidance: `docs/benchmarks.md`

## License

See `LICENSE`.
