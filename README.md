# Governance & Prompt System - Customer Overview

## README Index

This repository is split into a short customer-facing README and deep technical docs.

- Mandatory rules and system behavior -> [`master.md`](master.md)
- Technical and quality constraints -> [`rules.md`](rules.md)
- OpenCode setup and runtime behavior -> [`README-OPENCODE.md`](README-OPENCODE.md)
- Rulebook structure summary -> [`README-RULES.md`](README-RULES.md)
- Profiles and addons -> [`profiles/`](profiles/)
- Stability and release readiness contract -> [`STABILITY_SLA.md`](STABILITY_SLA.md)
- Session state schema -> [`SESSION_STATE_SCHEMA.md`](SESSION_STATE_SCHEMA.md)

This README is descriptive only. If this file conflicts with `master.md` or `rules.md`, treat this README as wrong.

## What This Is

This product is a deterministic governance system for AI-assisted software delivery.

- It gives teams a controlled start/continue/resume workflow with explicit gates.
- It prioritizes reviewability, traceability, and reproducible quality over speed.
- It ships customer-usable installers, templates, diagnostics contracts, and helper scripts.
- It supports repo-aware OpenCode mode and chat-only mode with the same governance core.
- It is designed for teams that need auditable delivery behavior (regulated or high-assurance environments).
- It is not aimed at throwaway prototypes or "move fast without evidence" workflows.

## Quick Start Matrix

- First-time install: run `python3 install.py` (or use the customer bundle wrapper in `install/`).
- New repository or new ticket: run `/start`.
- Resume interrupted work: use `/continue` or `/resume` with existing session state.
- Customer handoff install: deliver `customer-install-bundle-v1.zip` with `customer-install-bundle-v1.SHA256`.
- Release operations: use the release workflow path described in [`docs/releasing.md`](docs/releasing.md).
- Security evidence review: inspect `security_summary.json` as documented in [`docs/security-gates.md`](docs/security-gates.md).

## Installation

Default config root for customer installs is typically `~/.config/opencode` (platform details in [`docs/install-layout.md`](docs/install-layout.md)).

- Standard install: `python3 install.py`
- Deterministic dry-run first: `python3 install.py --dry-run`
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

See full path and layout details in [`docs/install-layout.md`](docs/install-layout.md).

## Documentation Map (Deep Docs)

- End-to-end phase map and gate behavior: [`docs/phases.md`](docs/phases.md)
- Install path variables and global layout: [`docs/install-layout.md`](docs/install-layout.md)
- Release workflows and one-command orchestration: [`docs/releasing.md`](docs/releasing.md)
- Quality benchmark packs and run flow: [`docs/benchmarks.md`](docs/benchmarks.md)
- Security scanners, fail-closed policy, and evidence semantics: [`docs/security-gates.md`](docs/security-gates.md)
- Customer bundle contract: [`docs/customer-install-bundle-v1.md`](docs/customer-install-bundle-v1.md)

## License

Distribution and usage terms are defined in [`LICENSE`](LICENSE).

Copyright (c) 2026 Benjamin Fuchs.
