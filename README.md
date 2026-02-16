# Governance & Prompt System - Customer Overview

- Codex/macOS App frontend surface (non-normative mirror) -> [AGENTS.md](AGENTS.md)
- OpenCode entrypoint / bootstrap adapter -> [start.md](start.md)
- Mandatory rules and system behavior -> [`master.md`](master.md)
- Technical and quality constraints -> [`rules.md`](rules.md)
- OpenCode setup and runtime behavior -> [`README-OPENCODE.md`](README-OPENCODE.md)
- Rulebook structure summary -> [`README-RULES.md`](README-RULES.md)
- Profiles and addons -> [`profiles/`](profiles/)
- Stability and release readiness contract -> [`STABILITY_SLA.md`](STABILITY_SLA.md)
- Session state schema -> [`SESSION_STATE_SCHEMA.md`](SESSION_STATE_SCHEMA.md)

This README is descriptive only. AGENTS.md is also non-normative; AGENTS.md is a non-normative mirror of master.md for agent frontends; conflicts resolve to master.md. If this file conflicts with `master.md`, `rules.md`, or AGENTS.md, treat the relevant non-normative surface as the source of truth.

## What This Is

This product is a deterministic governance system for AI-assisted software delivery.

- It also supports Codex App via AGENTS.md as a frontend surface, in addition to the OpenCode path.
- Model-agnostic: any LLM can be used under the same deterministic governance layer (via OpenCode).

- It gives teams a controlled start/continue/resume workflow with explicit gates.
- It prioritizes reviewability, traceability, and reproducible quality over speed.
- It ships customer-usable installers, templates, diagnostics contracts, and helper scripts.
- It supports repo-aware OpenCode mode and chat-only mode with the same governance core.
- It is designed for teams that need auditable delivery behavior (regulated or high-assurance environments).
- It is not aimed at throwaway prototypes or "move fast without evidence" workflows.

## Quick Start Matrix

- CLI/repository install flow: run `python3 install.py` (or use the customer bundle wrapper in `install/`).
- Codex App flow: open the repo in Codex; governance is loaded from AGENTS.md
- OpenCode session flow: run `/start` (OpenCode command, not a shell command).
- Resume interrupted work: use `/continue` or `/resume` with existing session state.
- Customer handoff install: deliver `customer-install-bundle-v1.zip` with `customer-install-bundle-v1.SHA256`.
- Release operations: use the release workflow path described in [`docs/releasing.md`](docs/releasing.md).
- Security evidence review: inspect `security_summary.json` as documented in [`docs/security-gates.md`](docs/security-gates.md).

## Installation

Config root is runtime-resolved by platform/environment settings (see OS-specific examples in [`docs/install-layout.md`](docs/install-layout.md)).

- Standard install: `python3 install.py`
- Deterministic dry-run first: `python3 install.py --dry-run`
- Installer-owned path binding file: `governance.paths.json` under `<config_root>/commands/` (Used by the OpenCode /start bootstrap; not required for AGENTS.md-frontends)
- Customer bundle install wrappers and handoff process: [`docs/customer-install-bundle-v1.md`](docs/customer-install-bundle-v1.md)

## Verify A Release

Use a short verification flow, then use deep docs if needed:

1. Verify checksum files (`SHA256SUMS.txt`, `customer-install-bundle-v1.SHA256`).
2. Verify Sigstore bundle identity constraints with `cosign verify-blob`.
3. Verify provenance/SBOM attestations with `gh attestation verify`.

Detailed verification policy and examples:

- [`docs/releasing.md`](docs/releasing.md)
- [`docs/release-security-model.md`](docs/release-security-model.md)

## Where Runtime State Lives

Runtime state is outside customer code repositories and lives under the config root.

- Active session pointer (global): `${SESSION_STATE_POINTER_FILE}`
- Repo-scoped session and persistence: `${WORKSPACES_HOME}/<repo_fingerprint>/...`
- Runtime error logs: `${WORKSPACES_HOME}/<repo_fingerprint>/logs/` (fallback `${CONFIG_ROOT}/logs/`)

See full path and layout details in [`docs/install-layout.md`](docs/install-layout.md). See start.md for the OpenCode bootstrap/binding evidence flow.

## Documentation Map (Deep Docs)

- End-to-end phase map and gate behavior: [`docs/phases.md`](docs/phases.md)
- Install path variables and global layout: [`docs/install-layout.md`](docs/install-layout.md)
- Release workflows and one-command orchestration: [`docs/releasing.md`](docs/releasing.md)
- Quality benchmark packs and run flow: [`docs/benchmarks.md`](docs/benchmarks.md)
- Security scanners, fail-closed policy, and evidence semantics: [`docs/security-gates.md`](docs/security-gates.md)
- Mode-aware repo-doc handling and host-permission orchestration: [`docs/mode-aware-repo-rules.md`](docs/mode-aware-repo-rules.md)
- Customer bundle contract: [`docs/customer-install-bundle-v1.md`](docs/customer-install-bundle-v1.md)

## License

Distribution and usage terms are defined in [`LICENSE`](LICENSE).

Copyright (c) 2026 Benjamin Fuchs.
