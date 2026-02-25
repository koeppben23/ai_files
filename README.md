# Governance and Prompt System

Deterministic governance for AI-assisted software delivery with fail-closed gates, evidence requirements, and reproducible session state.

**[→ Get started in 5 minutes: QUICKSTART.md](QUICKSTART.md)**

Runtime contract boundary:
- SSOT routing/execution/validation is `${COMMANDS_HOME}/phase_api.yaml` enforced by `governance/kernel/*`.
- `rules.md` and active profile/addon rulebooks define engineering constraints and stack extensions.
- `README*` and `AGENTS.md` are descriptive operational guides only.

## Quick Links

- **[Quick Start Guide](QUICKSTART.md)** - 5-minute setup
- OpenCode bootstrap entrypoint: `start.md`
- Governance invariants checklist: `docs/governance_invariants.md`
- OpenCode operational guide: `README-OPENCODE.md`
- Rules structure overview: `README-RULES.md`
- Stability/release contract: `STABILITY_SLA.md`
- Canonical session-state schema: `SESSION_STATE_SCHEMA.md`

## Audience

For engineering teams that need deterministic, auditable AI-assisted delivery in review-heavy or regulated environments.

## What This Repository Provides

- Deterministic phase workflow (`1` through `6`) with explicit gate outcomes.
- Repo-aware governance runtime under `governance/` with tested fail-closed semantics.
- Installer and customer handoff flow (`install.py`, release/bundle docs).
- Governance schema and policy contracts under `governance/`.
- Profile and addon ecosystem under `profiles/`.

## Quick Start

- Install locally: `${PYTHON_COMMAND} install.py`
- Run deterministic dry-run first: `${PYTHON_COMMAND} install.py --dry-run`
- In OpenCode, start a governed session with `/start`
- Continue an active session with `/continue` or `/resume`

Note: installer-owned path binding evidence is written to `<config_root>/commands/governance.paths.json` and is required for canonical OpenCode bootstrap behavior.

## Support Matrix

- Operating systems: macOS, Linux, Windows (path resolution is defined by installer binding + kernel loaders; examples in `docs/install-layout.md`).
- Runtime requirements: `${PYTHON_COMMAND}` for installer/governance helpers; `git` is recommended and required by identity-gated workflows.
- Frontend surfaces: OpenCode (`/start`, `/continue`, `/resume`, `/audit`) and Codex-style frontend surfaces via `AGENTS.md` mirror semantics.

## 60-Second Install Verification

Run the following after checkout or after installation:

```bash
${PYTHON_COMMAND} install.py --dry-run
${PYTHON_COMMAND} install.py
${PYTHON_COMMAND} install.py --status
```

Expected outcome:

- `--dry-run` reports planned actions without writes.
- install run completes without blocker reason codes.
- `--status` reports installed governance assets and healthy path bindings.

Then, in OpenCode, run `/start` and confirm bootstrap succeeds without binding/path blockers.

## Troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun `${PYTHON_COMMAND} install.py`, then verify with `${PYTHON_COMMAND} install.py --status`.
- `BLOCKED-VARIABLE-RESOLUTION`: check resolved config root/path bindings against `docs/install-layout.md`.
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure repository is a git checkout and `git` is available in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE`: provide missing evidence artifacts and rerun the gate.
- `NOT_VERIFIED-EVIDENCE-STALE`: refresh evidence (new probe/measurement) and rerun.

Deep security and governance references are in `docs/security-gates.md` and `docs/phases.md`.

## Version and Compatibility

- This README tracks the current repository baseline; runtime behavior is determined by kernel + `${COMMANDS_HOME}/phase_api.yaml`.
- For release readiness and compatibility gates, always apply `STABILITY_SLA.md` and the release process in `docs/releasing.md`.

## Runtime State and Paths

Canonical variables are resolved from installer-owned binding evidence and kernel policy loaders.

- Global active session pointer: `${SESSION_STATE_POINTER_FILE}`
- Repo-scoped workspace/session artifacts: `${WORKSPACES_HOME}/<repo_fingerprint>/...`
- Runtime error logs: `${WORKSPACES_HOME}/<repo_fingerprint>/logs/error.log.jsonl` (fallback `${COMMANDS_HOME}/logs/error.log.jsonl`)

See `docs/install-layout.md` for full layout details.

## Related Docs

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
