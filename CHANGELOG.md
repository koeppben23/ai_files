# Changelog
All notable changes to this project will be documented in this file.

This project follows **Keep a Changelog** and **Semantic Versioning**.

## [Unreleased]

### Added
- Add `STABILITY_SLA.md` as a normative 10-point governance stability Go/No-Go contract with explicit operational PASS/FAIL criteria.
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
- Add guided profile-selection behavior for ambiguous detection: system now emits ranked profile suggestions with evidence and requests explicit numbered selection (`1..n`, including `fallback-minimum`) while remaining fail-closed (`BLOCKED-AMBIGUOUS-PROFILE`) until clarified.
- Add UX execution contracts for deterministic operator flow: unified `[NEXT-ACTION]` footer, standardized blocked envelope fields, startup `[START-MODE]` banner, `[SNAPSHOT]` confidence/risk/scope block, and blocker `QuickFixCommands` guidance.
- Tighten UX contract coherence: add `0=abort/none` profile-choice escape, require command-field consistency across `[NEXT-ACTION]`/`next_command`/`QuickFixCommands[0]`, and require deterministic ordering for `missing_evidence`/`recovery_steps`.
- Add Architect-only Autopilot lifecycle contract (`/start` -> `/master` -> `Implement now` -> `Ingest evidence`) with explicit output-mode enum (`ARCHITECT|IMPLEMENT|VERIFY`) and fail-closed `/master` start-order gate (`BLOCKED-START-REQUIRED`).
- Tighten `start.md` evidence boundaries: missing installer-owned `governance.paths.json` now yields explicit blocked fallback semantics (`BLOCKED-MISSING-BINDING-FILE`) and marks computed path payloads as non-evidence debug output.
- Clarify `start.md` auto-persistence identity semantics so helper output is operational status only and cannot be treated as canonical repo identity evidence.
- Align governance factory contracts (`new_addon.md`, `new_profile.md`, `PROFILE_ADDON_FACTORY_CONTRACT.json`) with current canonical runtime policy: required surface ownership fields, capability-first manifest guidance, preferred profile filename pattern (`rules_<profile_key>.md`), canonical SESSION_STATE evidence paths, and clarified tracking/audit semantics.
- Clarify diagnostics reason-key boundaries: `/audit` `BR_*` keys are audit-only (not canonical `reason_code` values) unless explicitly mapped to `BLOCKED-*|WARN-*|NOT_VERIFIED-*` codes.
- Harden precedence drift detection with context-sensitive guards for numbered lists near precedence/priority/resolution language, preventing legacy shortened precedence variants from slipping through.
- Tighten capability signal-mapping checks to require concrete `signals.any` + non-empty entries (instead of broad indentation heuristics) for capability coverage validation.
- Add explicit claim-mapping regression test proving `result=pass` alone is insufficient for `verified` without scope/artifact/pinning evidence.
- Remove secondary precedence phrasing in `master.md` and enforce single canonical precedence authority with additional lint/test drift guards.
- Clarify ambiguity handling as planning-only unless clarified, and require `BLOCKED-AMBIGUOUS-PROFILE` when ambiguity affects tooling/architecture/gates.
- Align `/start` discovery contract with runtime override/fallback semantics (`${REPO_OVERRIDES_HOME}`, `${OPENCODE_HOME}`) without weakening installer-owned entrypoint roots.
- Add explicit BuildEvidence -> claim verification mapping (`verified` vs `not-verified`) and top-tier missing-file blocking semantics for Phase 4+.
- Wire Stability-SLA into normative governance docs (`master.md`, `rules.md`) as a release/readiness gate.
- Extend governance lint + governance tests to enforce Stability-SLA presence, canonical section tokens, and CI gate alignment.
- Clarify SLA regression gates to explicitly require both governance validation (`pytest -m governance`) and governance e2e flow coverage (`pytest -m e2e_governance`).
- Harden precedence drift detection: fail on duplicate/legacy precedence fragments and require canonical addon/template layer wording.
- Add high-ROI governance hardening invariants: capability catalog completeness checks, template evidence-kind gating, and activation delta bit-identity coverage.
- Add proof-carrying explain output requirements (`/why-blocked`, `/explain-activation`) with mandatory trigger facts and decision trace.
- Add evidence leakage guards for scoped/ticketed verification (`ticket_id`, `session_run_id`, scope leak constraints under ComponentScopePaths).
- Add deterministic activation-delta contract (`ActivationDelta.AddonScanHash`, `ActivationDelta.RepoFactsHash`, `BLOCKED-ACTIVATION-DELTA-MISMATCH`).
- Add toolchain pinning evidence policy for verified build/test claims (Java/Node/Maven/Gradle version evidence or `not-verified`).
- Introduce capability-first activation contracts (`RepoFacts.Capabilities` + `CapabilityEvidence`) with hard-signal fallback and deterministic `BLOCKED-MISSING-EVIDENCE` handling.
- Extend addon manifests/validator/lint with capability declarations (`capabilities_any` / `capabilities_all`) for normalized activation matching.
- Add governance coverage for capability-first activation, including e2e simulation for capability match + fallback hard-signal activation.
- Add a machine-readable diagnostics payload contract for emitted reason codes (`BLOCKED-*`, `WARN-*`, `NOT_VERIFIED-*`) with required fields (`reason_code`, `surface`, `signals_used`, `recovery_steps`, `next_command`) in master/schema/tests.
- Add SESSION_STATE versioning + migration contract (`session_state_version`, `ruleset_hash`) with deterministic upgrade-or-block behavior (`BLOCKED-STATE-OUTDATED`).
- Add a fast governance lint layer (`scripts/governance_lint.py`) and CI `governance-lint` fail-fast job for structural invariants (priority uniqueness, anchor presence, manifest contract, required rulebook references).
- Add addon surface ownership governance (`owns_surfaces`, `touches_surfaces`) with deterministic conflict prevention and lint/validator/test enforcement.
- Add read-only operator explain contracts (`/why-blocked`, `/explain-activation`) with deterministic output requirements and no state mutation/evidence fabrication.
- Enrich BuildEvidence schema for reproducibility (`scope_paths`, `modules`, typed `artifacts`, optional `command_line`, `env_fingerprint`).
- Add correctness-by-construction template contracts (inputs, guaranteed outputs, evidence expectations, golden+anti examples) for core template rulebooks.
- Add a deterministic addon/template tie-break contract and explicit `BLOCKED-ADDON-CONFLICT` path in `master.md` + `rules.md` to avoid same-precedence activation ambiguity.
- Add a monorepo scope invariant contract test ensuring missing `ComponentScopePaths` at code-phase maps to `BLOCKED-MISSING-EVIDENCE` when addon activation would otherwise be repo-wide/ambiguous.
- Clarify control-plane terminology: "repo working tree" vs workspace bucket paths, and restrict rulebook loading to trusted outside-repo governance roots.
- Align Master priority order with canonical precedence by explicitly inserting activated templates/addons between active profile and ticket specification.
- Clarify addon activation semantics by separating evidence-based activation requirement (`AddonsEvidence.*.required`) from manifest policy class (`addon_class`).
- Clarify workspace override pathing by introducing `${REPO_OVERRIDES_HOME}` and replacing `${REPO_HOME}/governance/...` search examples with explicit outside-repo override paths.
- Add a first-class operator reload contract (`/reload-addons`) that deterministically executes only Phase 1.3 + 1.4, refreshes load/evidence pointers, and forbids auto-advance.
- Remove `README-RULES.md` from normative priority order and mark it explicitly as non-normative executive summary.
- Require a terminal `NEXT_STEP: <SESSION_STATE.Next>` line after every `SESSION_STATE` output, and codify this in `master.md` + `SESSION_STATE_SCHEMA.md` with governance tests.
- Enforce Conventional naming for assistant-created branches/commits in governance contracts and CI (`master.md`, `rules.md`, `.github/workflows/ci.yml`) including PR branch-name and commit-subject validation.
- Standardize `profiles/rules*.md` operational wrappers with consistent headings (`Intent`, `Scope`, `Activation`, `Phase integration`, `Evidence contract`, `Tooling`, `Examples`, `Troubleshooting`) and normalize quick-block variants to canonical section headings.
- Replace fragile `rules.md Section 4.6` references with stable anchor references (`RULEBOOK-PRECEDENCE-POLICY`) across profiles, factory templates, master guidance, and governance tests.
- Canonicalize required-vs-advisory addon behavior as a single fail-closed policy source in `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY` plus `master.md` addon catalog (local rulebooks now reference, not redefine, blocking semantics).
- Add a governed emergency override contract for missing required addons (ticket/incident id, reason, approver, expiry/remediation, and mandatory `not-verified` status for affected claims).
- Normalize template/profile rulebooks to remove local `Mode = BLOCKED` policy definitions in favor of canonical required-addon handling references:
  - `rules.backend-java-templates.md`
  - `rules.backend-java-kafka-templates.md`
  - `rules.frontend-angular-nx-templates.md`
  - `rules.frontend-angular-nx.md`
- Strengthen operational actionability with explicit examples/troubleshooting expansions in:
  - `rules.backend-java-templates.md`
  - `rules.backend-java-kafka-templates.md`
  - `rules.cucumber-bdd.md`
- Make fallback governance evidence contract explicit in `rules.fallback-minimum.md` (`BuildEvidence`, `warnings[]`, `not-verified` enforcement).
- Tighten docs-governance terminology safety: BLOCKED aliases are now explicitly marked as legacy vocabulary that advisory addons must not emit.
- Extend governance regression guards to enforce:
  - canonical policy centralization (no local blocking-policy redefinition)
  - examples/troubleshooting presence in reviewed rulebooks
  - explicit fallback evidence-contract tokens
  - docs-governance legacy BLOCKED alias safeguards
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
- Normalize remaining profile-rulebook polish details after shared modularization (remove mid-file end markers, keep copyright/footer ordering consistent).
- Set shared governance addon activation signals to cross-stack `file_glob: "**/*"` for deterministic loading across non-Java repositories.
- Strengthen workflow guarantees for shared modularization in installer/e2e tests (shared addons copied, manifest-listed, and advisory-missing behavior verified as non-blocking).
- Harden profile auto-detection semantics: profile candidate selection now explicitly excludes addon-referenced and shared governance rulebooks.
- Normalize footer/marker consistency across `profiles/rules*.md` after modularization (remove mid-file end markers, align copyright placement/style).

### Fixed
- Extend `persist_workspace_artifacts.py --quiet` blocked output with structured reason fields (`reason_code`, `recovery_steps`, `next_command`) for direct `SESSION_STATE.Diagnostics.ReasonPayloads` integration.
- Include addon manifests (`profiles/addons/*.addon.yml`) in release artifacts so runtime addon activation/reload works from packaged RC builds.
- Remove duplicate local `_pretty` function definition in `scripts/build.py` to keep release artifact logging implementation clean and deterministic.
- Uninstall now purges installer/runtime-owned `errors-*.jsonl` logs by default (with `--keep-error-logs` opt-out), while preserving non-matching user files.
- Fix backend-java evidence gate wording to block pass at Phase 5.3/6 when required evidence is missing.

### Security
- Tighten principal-grade declaration rules: incomplete or non-comparable scorecard data must emit `WARN-SCORECARD-CALIBRATION-INCOMPLETE` and remain `not-verified`.

## [1.1.0-RC.2] - 2026-02-09
### Changed
- Promote governance release marker to `1.1.0-RC.2` across canonical version sources (`master.md`, `install.py`) after merging UX/autopilot lifecycle and README alignment hardening.

## [1.1.0-RC.1] - 2026-02-08
### Changed
- Promote current governance release classification from Beta to Release Candidate (`1.1.0-RC.1`) across canonical version sources (`master.md`, `install.py`).

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
