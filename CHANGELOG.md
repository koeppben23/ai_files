# Changelog
All notable changes to this project will be documented in this file.

This project follows **Keep a Changelog** and **Semantic Versioning**.

## [Unreleased]

### Added
- Add a shared `Principal Excellence Contract` baseline across all governance profile rulebooks under `profiles/rules*.md`.
- Add Java-first principal hardening v2 contracts for backend quality gates:
  - `rules.backend-java.md` (risk tiering, mandatory evidence packs, hard-fail criteria, determinism budget)
  - `rules.backend-java-templates.md` (template conformance + evidence artifact contract)
  - `rules.backend-java-kafka-templates.md` (Kafka critical gate + idempotency/retry/async test requirements)
- Add hardening v2 contracts for previously lightweight rulebooks:
  - `rules.frontend-cypress-testing.md`
  - `rules.frontend-openapi-ts-client.md`
  - `rules.fallback-minimum.md`
- Add cross-addon normalization contracts:
  - `Principal Hardening v2.1 - Standard Risk Tiering`
  - `Principal Hardening v2.1.1 - Scorecard Calibration`
- Add governance factory commands for principal-grade extension work:
  - `new_profile.md` for generating new profile rulebooks
  - `new_addon.md` for generating addon rulebook + manifest pairs
- Add diagnostics contract `diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json` to standardize factory output requirements.
- Add diagnostics recovery helper `diagnostics/bootstrap_session_state.py` to initialize repo-scoped `${SESSION_STATE_FILE}` plus global `${SESSION_STATE_POINTER_FILE}` when session state is missing.
- Add diagnostics helper `diagnostics/persist_workspace_artifacts.py` to backfill missing repo-scoped persistence artifacts (`repo-cache.yaml`, `repo-map-digest.md`, `decision-pack.md`, `workspace-memory.yaml`).
- Add structured runtime error logging helper `diagnostics/error_logs.py` (`opencode.error-log.v1`) with repo-scoped and global JSONL targets.
- Add runtime error index summaries (`errors-index.json`) and automatic retention pruning for old `errors-*.jsonl` files (default 30 days).
- Add shared advisory governance rulebooks and manifests for cross-profile contracts:
  - `rules.principal-excellence.md`
  - `rules.risk-tiering.md`
  - `rules.scorecard-calibration.md`
  - manifests: `principalExcellence`, `riskTiering`, `scorecardCalibration`
- Update factory contracts (`new_profile.md`, `new_addon.md`, `PROFILE_ADDON_FACTORY_CONTRACT.json`) for shared-contract modularization defaults.

### Changed
- Normalize governance evaluation semantics across add-ons/templates with canonical tier labels (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`), fixed score thresholds, and a unified calibration version (`v2.1.1`).
- Strengthen scorecard comparability and claim-to-evidence expectations so multi-addon reviews use the same pass/fail interpretation.
- Extend v2.1 and v2.1.1 calibration blocks to all remaining profile rulebooks (`rules.backend-java.md`, `rules.frontend-angular-nx.md`, `rules.fallback-minimum.md`) for complete cross-profile consistency.
- Clarify installer docs with explicit diagnostics contract reference (`PROFILE_ADDON_FACTORY_CONTRACT.json`).
- Shift canonical session storage topology to repo-scoped `${SESSION_STATE_FILE}` with global `${SESSION_STATE_POINTER_FILE}` as active pointer for multi-repo safety.
- `/start` now includes an auto-persistence hook that calls the workspace artifact backfill helper when available.
- Improve workspace artifact routing safety: backfill helper now resolves repo fingerprint from current repo git metadata before using global pointer fallback, reducing stale-pointer cross-repo writes.
- Add governance guardrails/tests to enforce that Phase 2.1 always surfaces the Phase 1.5 A/B decision prompt when Phase 1.5 was neither explicitly requested nor skipped.
- Extend `/start` + diagnostics helpers to emit automatic structured error logs, and expose error-log paths in `governance.paths.json` (`globalErrorLogsHome`, `workspaceErrorLogsHomeTemplate`).
- Installer now patches installer-owned legacy `governance.paths.json` files with missing error-log path keys even without `--force`.
- Refine `rules.backend-java.md` to remove Kafka activation ambiguity, use canonical shared tiering semantics, and delegate shared principal contracts to modular advisory rulebooks.
- Migrate all remaining `rules*.md` rulebooks to shared principal-governance modularization (delegation to shared advisory rulebooks).

### Fixed
- Remove duplicate local `_pretty` function definition in `scripts/build.py` to keep release artifact logging implementation clean and deterministic.
- Uninstall now purges installer/runtime-owned `errors-*.jsonl` logs by default (with `--keep-error-logs` opt-out), while preserving non-matching user files.
- Fix backend-java evidence gate wording to block pass at Phase 5.3/6 when required evidence is missing.

### Security
- Tighten principal-grade declaration rules: incomplete or non-comparable scorecard data must emit `WARN-SCORECARD-CALIBRATION-INCOMPLETE` and remain `not-verified`.

## [1.1.0-BETA] - 2026-02-06
### Added
- Initialize post-1.0.1-BETA development baseline.
- Add PostgreSQL + Liquibase governance profile (`rules.postgres-liquibase`).
- Add frontend Angular/Nx governance expansion:
  - `rules.frontend-angular-nx.md`
  - `rules.frontend-angular-nx-templates.md` (required addon)
  - `rules.frontend-cypress-testing.md` (advisory addon)
  - `rules.frontend-openapi-ts-client.md` (advisory addon)
- Add addon manifest classes (`addon_class: required|advisory`) and frontend addon manifests under `profiles/addons/`.
- Add governance diagnostics script `scripts/validate_addons.py` (manifest structure + class/signal validation).
- Add CI-governed end-to-end flow coverage for addon activation/reload (`tests/test_governance_e2e_flow.py`, `governance-e2e` job).
- Add Mandatory Review Matrix (MRM) and Gate Scorecard governance contracts for reviewer-proof PR readiness.

### Changed
- Align full phase-flow semantics across `master.md`, `rules.md`, `SESSION_STATE_SCHEMA.md`, and README docs (including 2.1/1.5/5.3/5.4/5.6 behavior).
- Normalize persistence/path documentation and install layout diagrams to match actual installer behavior.
- Installer now copies addon manifests to `commands/profiles/addons/` and includes them in `INSTALL_MANIFEST.json`.
- Uninstall fallback safety hardened to resolve installer-owned targets from source/manifests instead of broad recursive deletion.
- Token-efficiency improved via deferred/lazy rulebook activation clarifications, reuse/delta-reload guidance, and compacted phase output templates.
- Governance release/readiness rules tightened with claim-to-evidence mapping and cross-repo impact requirements for contract/schema changes.

### Fixed
- Resolve addon blocking-policy inconsistencies (`required` blocks, `advisory` warns) across master/schema/profiles.
- Fix stale/incorrect profile references (`rules.frontend.md` -> `rules.frontend-angular-nx.md`).
- Fix path ownership docs for global session files vs repo-scoped workspace artifacts.
- Fix cucumber lint example regex/control-character issue in profile documentation.
- Fix missing canonical BLOCKED code coverage (`BLOCKED-VARIABLE-RESOLUTION`) in schema consistency.
- Fix E2E addon trigger matching edge cases and extend signal handling (`file_glob`, `workflow_file`, `maven_dep`, `maven_dep_prefix`, `code_regex`, `config_key_prefix`).

### Removed

### Security
- Strengthen fail-closed behavior for required addon/rulebook absence and missing evidence scenarios.
- Increase review hardening via mandatory gate artifacts/scorecards and final review-of-review consistency checks.
## [1.0.1-BETA] - 2026-02-06
### Added
- PR-gated “Release Readiness” workflow to enforce branch protection on `main`.

### Changed
- Release automation now enforces LF newlines across platforms.
- Pre-release handling extended for `-BETA`, `beta.x`, and `rc.x` identifiers.

### Fixed
- Release dry-run no longer introduces newline drift on Windows systems.
- Version propagation is now fully consistent across governance files.

### Removed

### Security
- Release pipeline blocks execution on dirty git working trees.

## [1.0.0-BETA] - 2026-02-06
### Added
- Deterministic installer (`install.py`) with **mandatory** governance version.
- Manifest-based uninstall: the manifest is the *only* delete source.
- Deterministic release artifacts (`scripts/build.py`) producing `zip` + `tar.gz` and `SHA256SUMS.txt`.
- CI spec guards (fail-fast) for drift prevention.

### Changed
- Windows-safe conventions: path variables (`${CONFIG_ROOT}`) and case-collision protection.

### Fixed
- Packaging drift / legacy artifacts removed (no unresolved placeholders, no `opencode.json` remnants).
- Uninstall fallback hardened to not depend on the repo source directory.

### Security
- Hard CI gates to block silent fallback behavior and prevent spec drift.
