# Changelog
All notable changes to this project will be documented in this file.

This project follows **Keep a Changelog** and **Semantic Versioning**.

## [Unreleased]

### Added
- Add backend Python profile rulebook `profiles/rules.backend-python.md` with deterministic evidence, tooling, migration/rollback, and operational safety contracts.
- Add backend Python templates addon pair:
  - `profiles/rules.backend-python-templates.md` (required code-generation template contract)
  - `profiles/addons/backendPythonTemplates.addon.yml` (capability/signal activation policy)
- Add Python quality benchmark artifacts:
  - `diagnostics/PYTHON_QUALITY_BENCHMARK_PACK.json` (5-task benchmark + scoring rubric)
  - `docs/python-quality-benchmark-pack.md` (operator runbook and comparison guidance)
- Add benchmark-pack coverage for all active profiles:
  - `diagnostics/BACKEND_JAVA_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/FRONTEND_ANGULAR_NX_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/OPENAPI_CONTRACTS_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/CUCUMBER_BDD_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/POSTGRES_LIQUIBASE_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/FRONTEND_CYPRESS_TESTING_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/FRONTEND_OPENAPI_TS_CLIENT_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/DOCS_GOVERNANCE_QUALITY_BENCHMARK_PACK.json`
  - `diagnostics/FALLBACK_MINIMUM_QUALITY_BENCHMARK_PACK.json`
  - `docs/quality-benchmark-pack-matrix.md`
- Add benchmark runner script `scripts/run_quality_benchmark.py` to execute pack scoring with evidence gates (`PASS`/`FAIL`/`NOT_VERIFIED`) and machine-readable output.
- Add operator-facing benchmark execution guidance in `README.md` (pack selection, run flow, evidence/scoring contract) with Python runbook linkage.
- Refresh `README.md` operational guidance to use `/start` as primary workflow entrypoint and update shipped artifact/directory mapping for current releases.
- Add deterministic SESSION_STATE migration tool `scripts/migrate_session_state.py` with first-write `.backup` behavior and machine-readable exit codes (`0=ok`, `2=blocked`).
- Add two-layer render modules under `governance/render/` (`intent_router.py`, `delta_renderer.py`, `token_guard.py`, `render_contract.py`) for compact default output and deterministic detail expansion.
- Add engine lifecycle helpers in `governance/engine/lifecycle.py` for staged activation pointer handling, automatic rollback, and rollback audit `DEVIATION` payloads.
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
- Installer now ships the governance runtime package (`governance/**`) into `commands/governance/**` so state-machine modules are available from installed command surfaces without repo-local imports.
- Align state-machine governance contracts for strict snapshot-first output, full-state YAML block semantics, and canonical reason-code casing parity across docs/runtime/tests.
- Complete SESSION_STATE rollout hardening through phase 3 (legacy removed), including explicit compatibility semantics and deterministic fail-closed recovery guidance.
- Add claim-evidence backfeed from `SESSION_STATE.BuildEvidence` with freshness/TTL gating and canonical stale-evidence status `NOT_VERIFIED-EVIDENCE-STALE`.
- Add release/build-time README baseline claim guards and local README link-integrity verification in `scripts/build.py` with verification-report coverage.
- Consolidate README set for the rework baseline and remove obsolete `README-CHAT.md`.
- Add operator-first response layering contract across governance rulebooks: concise brief-first output with full diagnostics on explicit detail request.
- Refactor `/start` bootstrap prompt internals by extracting inline Python snippets into diagnostics helpers (`diagnostics/start_binding_evidence.py`, `diagnostics/start_preflight_persistence.py`) for maintainability.
- Improve `/start` recovery UX by preferring concrete, copy-paste runnable `next_command`/recovery commands and minimizing unresolved placeholders when runtime evidence can derive values.
- Clarify preflight UX with explicit `required_now` vs `required_later` reporting plus deterministic `block_now` signal, and add post-bootstrap conversational/language-adaptive follow-up guidance.
- Improve `/why-blocked` UX contract with brief-first then detail payload layering.
- Add deterministic compact `status_tag` contract (`<PHASE>-<GATE>-<STATE>`) for faster operator scanning.
- Add recommended quick-fix command confidence labels (`safe` / `review-first`) for blocker recovery guidance.
- Strengthen `NextAction` wording contract to prefer concrete phase/gate/scope context over generic continuation phrasing.
- Add compact mode-transition summary line contract (`[TRANSITION] from -> to | reason: ...`).
- Add explicit `state_unchanged` acknowledgment guidance for no-transition responses.
- Add deterministic conversational post-start fixture intents (`what_phase`, `discovery_done`, `workflow_unchanged`) and governance tests.
- Add governance PR operator-impact note contract requiring `What changed for operators?` guidance in PR bodies.
- Add deterministic short-intent routing contract for post-start questions (`where_am_i`, `what_blocks_me`, `what_now`) with concise intent-first responses.
- Add compact phase progress bar contract (`phase_progress_bar`, e.g. `[##----] 2/6`) for faster operator orientation.
- Add top-1 blocker prioritization contract (`primary_reason_code`) so one primary blocker/command leads recovery.
- Add reason-code quick-fix template catalog (`diagnostics/QUICKFIX_TEMPLATES.json`) for reusable recovery guidance.
- Add delta-only no-change response contract (`state_unchanged` + `no_delta`) to reduce repetitive status noise.
- Add operator persona response modes (`compact`, `standard`, `audit`) as presentation-only controls.
- Add governance PR `Reviewer focus` guidance for high-risk contract deltas and targeted review hints.
- Add installer/release artifact coverage checks to require shipping `diagnostics/QUICKFIX_TEMPLATES.json`.
- Add deterministic conversational UX golden fixtures in `diagnostics/UX_INTENT_GOLDENS.json` with e2e regression validation for `where_am_i`, `what_blocks_me`, and `what_now` intents.
- Fix `/start` diagnostics bootstrap pathing to resolve installed helpers from `${COMMANDS_HOME}/diagnostics` instead of workspace-relative assumptions.
- Move `repo-identity-map.yaml` to repo workspace scope (`workspaces/<repo_fingerprint>/`) and align bootstrap persistence checks accordingly.
- Clarify unambiguous profile behavior: auto-load canonical rulebooks without asking operator to paste/provide rulebook files.
- Add `/start` invocation loop guard: when command context is injected, bootstrap proceeds immediately and does not re-request `/start` in the same turn.
- Make workspace persistence bootstrap diagnostics non-blocking (`WARN-WORKSPACE-PERSISTENCE`) when repo fingerprint cannot be derived, so persistence remains operational convenience and not a hard gate.
- Enforce profile autodetect-first behavior when multiple rulebooks are present: rank by repo/ticket signals and auto-select unique top candidate before prompting manual selection.
- Prevent Business Rules fallback target drift: on write failures keep `${REPO_BUSINESS_RULES_FILE}` with `write-requested` and forbid redirecting BR inventory into `workspace-memory.yaml`/`SESSION_STATE`.
- Adjust `/start` persistence helper for host backup-path sessions: skip fingerprint-dependent backfill as `WARN` instead of error-blocking behavior when repo root is not a git checkout.
- Update backfill default recommendation for Phase 1.5 decision to lightweight discovery (`Recommendation: A`) and ensure `/start` does not demand ticket/task before Phase 4.
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
- Align bootstrap template state with canonical output-mode lifecycle (`SESSION_STATE.OutputMode=ARCHITECT`) and canonical start-order blocker (`Next=BLOCKED-START-REQUIRED`).
- Extend bootstrap session template with canonical state invariants (`session_state_version`, `ruleset_hash`, `DecisionSurface`) required by ARCHITECT-mode/session schema contracts.
- Tighten response-envelope schema to conditionally require blocker fields (`reason_payload`, `quick_fix_commands`) when `status=blocked`.
- Strengthen top-tier governance evidence by adding explicit `RulebookLoadEvidence.top_tier.*` expectations and clarifying conflict-model mapping as classifier-only (no second precedence model).
- Ensure bootstrap SESSION_STATE now seeds `RulebookLoadEvidence.top_tier` with canonical `QUALITY_INDEX.md` and `CONFLICT_RESOLUTION.md` load-evidence pointers.
- Add governance regression coverage for fail-closed Phase-4 behavior when top-tier rulebooks are unresolved (`BLOCKED-MISSING-RULEBOOK:<file>` contract token).
- Add deterministic audit-to-canonical reason bridge tooling (`diagnostics/map_audit_to_canonical.py`) with canonical mapping source (`diagnostics/AUDIT_REASON_CANONICAL_MAP.json`) and strict-unmapped mode.
- Harden audit bridge determinism by selecting `primaryReasonCode` via severity precedence (`BLOCKED-*` > `WARN-*` > `NOT_VERIFIED-*`) instead of first-seen order.
- Enforce distribution/install coverage for audit bridge assets (`diagnostics/map_audit_to_canonical.py`, `diagnostics/AUDIT_REASON_CANONICAL_MAP.json`) in build and installer policy tests.
- Clarify `/start` bootstrap evidence behavior to require host evidence attempt first (when `governance.paths.json` is readable) and defer profile rulebook selection to Phase 1.2/Post-Phase-2 detection.
- Tighten Phase 1.5 extraction contracts to require repository code/test evidence; README/documentation-only rules are now explicitly non-counting `CANDIDATE`s and cannot satisfy extracted business-rule claims.
- Add deterministic profile selection guidance for unambiguous Java backend repositories (`backend-java` default without explicit selection prompt).
- Harden `/start` binding hook failure reporting when `governance.paths.json` exists but is unreadable (`BLOCKED-VARIABLE-RESOLUTION`) and auto-bootstrap repo session state when persistence detects `no-session-file`.
- Add Phase-2 repo-root defaulting contract: when OpenCode host already provides indexed repository root, use it first and request access authorization before asking for manual repo path input.
- Clarify Phase 2.1 decision-pack flow to auto-run from repository evidence without requiring `ticketGoal`; `ticketGoal` is now explicitly mandatory at Phase 4 entry (Step 0) before code-producing work.
- Make `/start` workspace persistence diagnostics non-blocking (`WARN-WORKSPACE-PERSISTENCE`) when helper scripts are missing/failing, while keeping binding evidence fail-closed.
- Add host-constraint COMPAT mode contracts (`DEVIATION.host_constraint`, `RequiredInputs`, `Recovery`, `NextAction`) so governance remains deterministic without strict output-wrapper collisions.
- Preserve canonical lifecycle contract (`/start` -> `/master`) while keeping host-constraint COMPAT output behavior.
- Tighten `/start` binding blocker payloads with explicit `missing_evidence` and `next_command`, and remove normal-path wording that implied operator-evidence bypass for missing installer binding.
- Guard workspace persistence writes behind repo identity evidence presence (`repo-identity-map.yaml`), emitting non-blocking `WARN-WORKSPACE-PERSISTENCE` when identity evidence is unavailable.
- Clarify OpenCode Desktop host-constrained mapping: `/start` is the practical `/master`-equivalent entrypoint while preserving canonical `/master` semantics for hosts that support direct invocation.
- Adjust Phase 2/2.1 and Phase 1.5 exit contracts to avoid early ticket prompts when `ticketGoal` is missing; hold in ARCHITECT-ready state until ticket is provided or an explicit continue command is given.
- Improve enterprise-restricted fallback guidance: persistence blockers/skips now emit explicit `required_operator_action`, `feedback_required`, `missing_evidence`, and deterministic `next_command` fields so users can run manual recovery and report back.
- Enforce formatted `SESSION_STATE` output as fenced YAML across strict and COMPAT response modes to keep state blocks machine-readable and visually stable.
- Prevent early Phase-2 discovery prompts for ticket/change request by routing no-ticket cases through automatic Phase 3A/3B (including auto-not-applicable paths) and deferring ticket requests to Phase 4 entry.
- Refine `/start` no-filesystem fallback evidence wording so bootstrap asks only for `master.md` minimum and defers `rules.md`/profile contents to their phase gates.
- Add explicit lint/test regression guard to forbid reintroduction of legacy `/start` fallback text that requests full `master.md + rules.md + profile` contents during bootstrap.
- Normalize legacy workspace backfill placeholder phrasing (`Backfill placeholder`) on subsequent persistence runs even without `--force`, so persisted artifacts are refreshed to current wording in later phases.
- Tighten `SESSION_STATE` output contract: emitted state blocks must be fenced YAML with explicit values and no placeholder tokens (`...`, `<...>`) in strict or COMPAT mode.
- Bootstrap now writes/updates `${REPO_IDENTITY_MAP_FILE}` (`repo-identity-map.yaml`) so identity-gated persistence can continue deterministically after manual fingerprint bootstrap.
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
- Add a canonical structured response envelope schema contract (`diagnostics/RESPONSE_ENVELOPE_SCHEMA.json`) and wire `/start`/core rulebooks to require schema-aligned output fields.
- Narrow shared governance advisory addon activation signals from unbounded `**/*` to explicit governance entry signals (`master.md`) for cleaner capability/signal semantics.
- Clarify `CONFLICT_RESOLUTION.md` mapping so P-levels are conflict classifiers/tie-breakers only and never a second precedence model over `master.md`.

### Fixed
- Extend `persist_workspace_artifacts.py --quiet` blocked output with structured reason fields (`reason_code`, `recovery_steps`, `next_command`) for direct `SESSION_STATE.Diagnostics.ReasonPayloads` integration.
- Include addon manifests (`profiles/addons/*.addon.yml`) in release artifacts so runtime addon activation/reload works from packaged RC builds.
- Include diagnostics runtime Python helpers (`diagnostics/*.py`) in release artifacts so `/start` auto-persistence and runtime error logging remain available after install.
- Fix `/start` workspace persistence hook failure semantics to emit canonical blocked payloads (`BLOCKED-WORKSPACE-PERSISTENCE`) and write structured runtime error logs when the helper is missing or fails.
- Fix bootstrap diagnostics coverage by logging missing backfill helper events (`ERR-WORKSPACE-PERSISTENCE-HOOK-MISSING`) instead of silently skipping.
- Fix Business Rules inventory read path contract to use canonical `${REPO_BUSINESS_RULES_FILE}` instead of a non-canonical `${CONFIG_ROOT}/${REPO_NAME}/business-rules.md` fallback.
- Fix workspace persistence helper to auto-materialize `${REPO_BUSINESS_RULES_FILE}` and update `SESSION_STATE.BusinessRules.InventoryFileStatus=written` when Phase 1.5 state is marked as extracted.
- Remove duplicate local `_pretty` function definition in `scripts/build.py` to keep release artifact logging implementation clean and deterministic.
- Uninstall now purges installer/runtime-owned `errors-*.jsonl` logs by default (with `--keep-error-logs` opt-out), while preserving non-matching user files.
- Fix backend-java evidence gate wording to block pass at Phase 5.3/6 when required evidence is missing.
- Strengthen CI artifact smoke coverage to verify installed diagnostics runtime helpers exist and that `persist_workspace_artifacts.py` executes successfully from the installed payload.
- Add fail-closed governance guards for trusted rulebook discovery roots, canonical addon catalog boundaries, and RulebookLoadEvidence blocking semantics (`BLOCKED-RULEBOOK-EVIDENCE-MISSING`) in lint + governance tests.
- Add activation-delta regression coverage that deterministically blocks when activation outcome drifts while addon/repo-facts hashes are unchanged (`BLOCKED-ACTIVATION-DELTA-MISMATCH`).
- Fix Kafka addon capability gating to be Kafka-specific (remove broad `java`/`spring` capability activation that could over-trigger required Kafka constraints).
- Add installer distribution completeness gate coverage for required normative files (`QUALITY_INDEX.md`, `CONFLICT_RESOLUTION.md`, `STABILITY_SLA.md`, `SESSION_STATE_SCHEMA.md`) and addon-manifest rulebook resolvability after install.
- Add top-tier load-evidence contract fields for `QUALITY_INDEX.md` / `CONFLICT_RESOLUTION.md` (`RulebookLoadEvidence.top_tier.*`) in master/schema and governance tests.
- Add a response-contract validator (`scripts/validate_response_contract.py`) with governance checks for blocked-envelope coherence and RulebookLoadEvidence presence when rulebooks are loaded.

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
