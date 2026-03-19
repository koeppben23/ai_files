# Operator Runbook

> **Document type:** Rails (guidance only, not binding).
> Authoritative logic lives in the Python kernel and JSON/YAML catalogs.
> This document references but does not define contracts.

---

## 1. Health Checks

Run these commands to verify system health. All three must pass before
proceeding with any upgrade or troubleshooting.

### 1.0 Canonical operator path truth

- Config root: `~/.config/opencode` (`commands/`, `plugins/`, `workspaces/`, `bin/`)
- Local root: `~/.local/opencode` (`governance_runtime/`, `governance_content/`, `governance_spec/`, `governance/`, `VERSION`)
- Primary bootstrap command: `opencode-governance-bootstrap init --profile <solo|team|regulated> --repo-root <repo-root>`
- `python -m ...` invocation is internal/debug/compatibility only, not primary operator guidance.

### 1.1 Validate Rulebook

```bash
python scripts/validate_rulebook.py --all
```

Validates all YAML profile rulebooks against the governance schema.
Exit codes: `0` = valid, `1` = validation errors found, `2` = usage error.

For machine-readable output (CI integration):

```bash
python scripts/validate_rulebook.py --all --json
```

Produces a `governance.validate-rulebook-report.v1` JSON envelope.

### 1.2 Governance Lint

```bash
python scripts/governance_lint.py
```

Checks SSOT parity, version format consistency, artifact hash integrity,
and structural invariants. Exit code `0` means all checks pass.

### 1.3 Migration Status

```bash
python scripts/migrate_rulebook_schema.py --check
```

Reports whether any profile rulebooks need schema migration.
Use this before and after upgrades to confirm migration state.

### 1.4 Full Health Check (one-liner)

```bash
python scripts/validate_rulebook.py --all \
  && python scripts/governance_lint.py \
  && python scripts/migrate_rulebook_schema.py --check
```

---

## 2. Upgrade Procedure

### 2.1 Pre-Upgrade Checklist

- [ ] Run full health check (Section 1.4) and confirm all pass
- [ ] Note current governance version: `cat governance/VERSION`
- [ ] Back up profile rulebooks: `cp -r rulesets/ rulesets.bak/`
- [ ] Back up workspace state if applicable

### 2.2 Dry Run

```bash
python scripts/migrate_rulebook_schema.py --dry-run
```

Reviews what migrations would be applied without making changes.
Inspect the output before proceeding.

### 2.3 Execute Upgrade

```bash
python scripts/migrate_rulebook_schema.py --target-version <VERSION>
```

Replace `<VERSION>` with the target schema version.

### 2.4 Post-Upgrade Verification

```bash
# 1. Validate all rulebooks
python scripts/validate_rulebook.py --all

# 2. Run governance lint
python scripts/governance_lint.py

# 3. Confirm migration state
python scripts/migrate_rulebook_schema.py --check

# 4. Verify artifact integrity
python -c "from governance.infrastructure.artifact_integrity import verify_all_releases; r = verify_all_releases(); print('OK' if r.passed else r)"
```

All four commands must succeed before marking the upgrade complete.

---

## 3. Rollback Procedure

### 3.1 When to Rollback

Rollback if any of these occur after an upgrade:

- `validate_rulebook.py --all` reports new validation errors
- `governance_lint.py` exits non-zero
- Engine activation emits `BLOCKED-INTEGRITY-FAILED`
- Runtime behavior differs from pre-upgrade baseline

### 3.2 Current Limitation: Depth = 1

The rollback mechanism supports **one level of rollback** only (engine
pointer swap to previous release). Multi-level rollback is planned for
Phase A.4.

### 3.3 Execute Rollback

```bash
# Restore rulebook backups
cp -r rulesets.bak/ rulesets/

# Re-run migration check to confirm state
python scripts/migrate_rulebook_schema.py --check
```

### 3.4 Post-Rollback Verification

Run the full health check (Section 1.4) and confirm all three commands
pass. If they do not, escalate — the system may require manual
intervention beyond a simple rollback.

---

## 4. Troubleshooting: BLOCKED Reason Code Reference

The governance engine emits `BLOCKED-*` reason codes when a deterministic
policy gate cannot be satisfied. There are **67 registered codes** in the
Python SSOT (`governance/domain/reason_codes.py`).

Data sources merged below:
- **Registry:** `governance/assets/catalogs/reason_codes.registry.json` (59 entries)
- **Remediation map:** `governance/assets/catalogs/REASON_REMEDIATION_MAP.json` (21 entries)
- **YAML catalog:** `governance/assets/reasons/blocked_reason_catalog.yaml` (25 entries)

### 4.1 Bootstrap and Session State

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-BOOTSTRAP-NOT-SATISFIED` | Bootstrap gates are not satisfied; kernel cannot proceed. | Run the local bootstrap launcher to complete bootstrap evidence collection. |
| `BLOCKED-START-REQUIRED` | Valid bootstrap evidence is required before governance execution. | Run `opencode-governance-bootstrap init --profile <solo\|team\|regulated> --repo-root <repo>`. |
| `BLOCKED-MISSING-BINDING-FILE` | Installer-owned binding evidence file (`governance.paths.json`) is missing. | Run `python install.py` to create the binding file at `${COMMANDS_HOME}/governance.paths.json`. |
| `BLOCKED-MISSING-COMMANDS-HOME` | `commands_home` is missing, empty, or invalid. | Set `COMMANDS_HOME` environment variable or repair binding evidence: `export COMMANDS_HOME=/path/to/commands`. |
| `BLOCKED-VARIABLE-RESOLUTION` | Required canonical variables could not be resolved deterministically. | Run `opencode-governance-bootstrap init --profile <solo\|team\|regulated> --repo-root <repo>`. Check that `${USER_HOME}`, `${CONFIG_ROOT}`, `${COMMANDS_HOME}` resolve correctly. |
| `BLOCKED-MISSING-EVIDENCE` | Required activation evidence is missing for deterministic resolution. | Check `SESSION_STATE.Diagnostics.ReasonPayloads` for specifics. Run `opencode-governance-bootstrap init --profile <solo\|team\|regulated> --repo-root <repo>` to re-gather evidence. |
| `BLOCKED-STATE-OUTDATED` | Persisted session state is stale for current deterministic contract. | Run `opencode-governance-bootstrap init --profile <solo\|team\|regulated> --repo-root <repo>` to refresh bootstrap state. |
| `BLOCKED-RESUME-STATE-VIOLATION` | Persisted `SESSION_STATE` violates the canonical schema on resume. | Delete invalid state file and run `opencode-governance-bootstrap init --profile <solo\|team\|regulated> --repo-root <repo>`. |
| `BLOCKED-WORKSPACE-PERSISTENCE` | Workspace persistence contract failed for required artifacts. | Run `unset OPENCODE_FORCE_READ_ONLY` and verify write permissions for commands/workspaces paths. |
| `BLOCKED-WORKSPACE-MEMORY-INVALID` | Workspace memory state is invalid or corrupted. | Fix the YAML file or remove `${WORKSPACE_MEMORY_FILE}` and retry. |

### 4.2 Rulebook and Profile Resolution

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-MISSING-CORE-RULES` | Core rules file (`rules.md`) could not be loaded. | Restore `rules.md` at the expected governance path. Run installer repair if needed. |
| `BLOCKED-RULEBOOK-LOAD-FAILED` | Core rulebook load failed in the Rulebook-Load pre-planning activation path (Phase 1.3). | Verify `rules.md` exists and is readable. Run `/continue` to retry. |
| `BLOCKED-MISSING-RULEBOOK` | Unresolved top-tier rulebook file blocks activation. | Install or restore the missing rulebook at `${COMMANDS_HOME}/` or `${PROFILES_HOME}/`. |
| `BLOCKED-MISSING-PROFILE` | Required active profile is missing and cannot be resolved. | Select a valid profile or provide profile evidence. Run `/continue`. |
| `BLOCKED-AMBIGUOUS-PROFILE` | Profile resolution is non-deterministic due to ambiguity. | Select a profile from the ranked shortlist explicitly. |
| `BLOCKED-MISSING-TEMPLATES` | Required templates cannot be resolved or loaded. | Verify templates rulebook exists for the active profile. Run `/continue`. |
| `BLOCKED-MISSING-ADDON` | Required addon rulebook is missing and cannot be loaded. | Verify addon manifest in `${PROFILES_HOME}/addons/`. Run `/continue`. |
| `BLOCKED-ADDON-CONFLICT` | Activated addons have conflicting ownership or constraints. | Review addon manifests — ensure `owns_surfaces` is unique per surface. Deactivate or merge conflicting addons. |
| `BLOCKED-MISSING-DECISION` | No valid decision options can be produced for the current gate. | Provide required decision evidence or inputs. |
| `BLOCKED-RULEBOOK-EVIDENCE-MISSING` | Required evidence for rulebook claims is missing. | Verify rulebook file accessibility. Provide explicit load evidence if host tools unavailable. |

### 4.3 Activation and Hash Integrity

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-ACTIVATION-DELTA-MISMATCH` | Activation outcome differs while input hashes remain unchanged. | Clear `SESSION_STATE` cache and re-run the local bootstrap launcher. Report if mismatch persists. |
| `BLOCKED-RULESET-HASH-MISMATCH` | Observed ruleset hash does not match expected deterministic hash. | Recompute ruleset hash and refresh persisted state. |
| `BLOCKED-ACTIVATION-HASH-MISMATCH` | Observed activation hash does not match expected deterministic hash. | Regenerate activation metadata from current canonical inputs. |
| `BLOCKED-INTEGRITY-FAILED` | SHA256 hash of a governance release artifact does not match `hashes.json`. File may be corrupted or tampered with. | Rebuild governance release artifacts with `build_ruleset_lock.py` or restore from a known-good release. |
| `BLOCKED-FINGERPRINT-MISMATCH` | Session state fingerprint does not match live repo identity. | Re-bootstrap session state from current repo root. |
| `BLOCKED-RELEASE-HYGIENE` | Release hygiene checks failed under strict mode. | Fix release metadata and rerun hygiene selfcheck. |

### 4.4 Engine, Persistence, and Permissions

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-ENGINE-SELFCHECK` | Engine selfcheck failed and runtime activation is blocked. | Verify policy-bound config files exist and YAML parser is available. Run `opencode-governance-bootstrap init --profile <solo\|team\|regulated> --repo-root <repo>`. |
| `BLOCKED-REPO-IDENTITY-RESOLUTION` | Repository identity could not be resolved under active policy. | Provide git identity evidence or run from a valid repository root. |
| `BLOCKED-REPO-ROOT-NOT-DETECTABLE` | Repository root cannot be resolved deterministically. | Set `OPENCODE_REPO_ROOT` or pass explicit `--repo-root` pointing to a valid Git root. |
| `BLOCKED-SYSTEM-MODE-REQUIRED` | Requested surface requires stricter system mode. | Switch to system mode or narrow requested operation scope. |
| `BLOCKED-OPERATING-MODE-REQUIRED` | Requested operation violates operating-mode minimum requirements. | Use required mode or reduce operation scope. |
| `BLOCKED-PERMISSION-DENIED` | Host capabilities do not satisfy required permission policy. | Run with required host permissions or narrow target surface. |
| `BLOCKED-EXEC-DISALLOWED` | Command execution capability is disallowed for this run. | Enable required execution capability in host policy. |
| `BLOCKED-PERSISTENCE-TARGET-DEGENERATE` | Persistence target resolved to forbidden or degenerate location. | Provide a complete, multi-segment target path or use variable-based path expression. |
| `BLOCKED-PERSISTENCE-PATH-VIOLATION` | Persistence path violates allowed contract boundaries. | Use canonical workspace/config-root scoped persistence paths. Replace OS-specific paths with `${CONFIG_ROOT}` expressions. |
| `BLOCKED-SURFACE-CONFLICT` | Selected packs define conflicting surface ownership. | Resolve pack conflicts before activation. |
| `BLOCKED-PACK-LOCK-REQUIRED` | Pack lock is required but missing. | Generate deterministic pack lock and retry. |
| `BLOCKED-PACK-LOCK-INVALID` | Observed pack lock is invalid. | Regenerate pack lock from canonical manifest set. |
| `BLOCKED-PACK-LOCK-MISMATCH` | Observed pack lock hash differs from expected hash. | Sync lockfile with selected packs and engine version. |
| `BLOCKED-UNSPECIFIED` | Blocked decision without a more specific canonical reason code. | Inspect deterministic gate evidence in `SESSION_STATE` and map to specific reason code. |
| `BLOCKED-SESSION-STATE-LEGACY-UNSUPPORTED` | Legacy session-state format is unsupported in active rollout phase. | Migrate session state to current schema version. |

### 4.5 Model Identity

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-MODEL-IDENTITY-UNTRUSTED` | Model identity source is not trusted for the required operation. | Set model identity from installer-owned binding file (`OPENCODE_BINDING_FILE`). |
| `BLOCKED-MODEL-CONTEXT-LIMIT-REQUIRED` | Pipeline mode requires explicit model context limit from `binding_env`. | Set `OPENCODE_MODEL_CONTEXT_LIMIT` in binding file. Only `binding_env` is trusted in pipeline. |
| `BLOCKED-MODEL-CONTEXT-LIMIT-UNKNOWN` | Model context limit could not be determined from any source. | Explicitly set `OPENCODE_MODEL_CONTEXT_LIMIT`. Hardcoded inference is not permitted. |
| `BLOCKED-MODEL-CONTEXT-LIMIT-INVALID` | Model context limit is invalid (negative value). | `context_limit` must be >= 0. Negative values are invalid in all modes. |
| `BLOCKED-MODEL-METADATA-FETCH-FAILED` | Provider metadata API fetch failed. | Check provider API connectivity or use explicit context limit from activation pack. |
| `BLOCKED-MODEL-IDENTITY-SOURCE-INVALID` | Model identity source is not a valid trust level. | Use one of: `binding_env`, `host_capability`, `provider_metadata`, `process_env`, `llm_context`, `user_input`, `inferred`, `unresolved`. |

### 4.6 Install Subsystem

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-INSTALL-PRECHECK-MISSING-SOURCE` | Installer precheck failed because required source artifacts are missing. | Restore installer source files or extract a valid release bundle. |
| `BLOCKED-INSTALL-VERSION-MISSING` | Installer could not find governance version metadata. | Ensure `governance/VERSION` contains a valid semantic version. |
| `BLOCKED-INSTALL-CONFIG-ROOT-INVALID` | Installer config root is invalid or unusable. | Provide a writable canonical config root and rerun installer. |

### 4.7 Migration and Schema

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-MISSING-DB-VERSION` | Database version metadata is missing. | Ensure schema version metadata is present in the target artifact. |
| `BLOCKED-FORMAT-UNDEFINED` | Schema format is undefined for the target artifact. | Define the schema format before attempting migration. |
| `BLOCKED-MIGRATION-UNSAFE` | Migration is unsafe — data loss or incompatibility detected. | Review migration plan. Use `--dry-run` to inspect changes before applying. |
| `BLOCKED-MIGRATION-NO-ROLLBACK` | Migration has no rollback path. | Ensure backup exists before proceeding. Current rollback depth = 1. |
| `BLOCKED-MIGRATION-COMPATIBILITY` | Migration target is incompatible with current schema. | Check version compatibility matrix in migration scripts. |

### 4.8 Pipeline Mode

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-PIPELINE-INTERACTIVE` | Pipeline mode cannot satisfy interactive approval requirements. | Fix pipeline configuration — pipeline mode forbids interactive prompts. |
| `BLOCKED-PIPELINE-HUMAN-ASSIST` | Pipeline mode requires human approval, which is not available. | Fix pipeline configuration or switch to user/agents_strict mode. |
| `BLOCKED-PIPELINE-PROMPT-BUDGET` | Prompt budget exceeded for the active mode. | Reduce prompts or increase budget through explicit policy change. |

### 4.9 Phase Gates

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-P5-3-TEST-QUALITY-GATE` | Phase 4 plan missing required Test Strategy subsection. | Add Test Strategy subsection to Phase 4 plan and re-evaluate P5.3 gate. |
| `BLOCKED-P5-4-BUSINESS-RULES-GATE` | Business rules coverage gap detected (>30% uncovered). | Ensure at least 70% of discovered business rules have coverage evidence. |
| `BLOCKED-P5-5-TECHNICAL-DEBT-GATE` | P5.5 Technical Debt gate not approved before Phase 6 entry. | Set `Gates["P5.5-TechnicalDebt"]` to `approved` or `not-applicable` and re-evaluate. |
| `BLOCKED-P5-6-ROLLBACK-SAFETY-GATE` | Rollback strategy missing or incomplete for schema/contract changes. | Provide `RollbackStrategy` with `DataMigrationReversible=true` or explicit safety steps. |
| `BLOCKED-REVIEW-DECISION-INVALID` | Review decision submitted via `/review-decision` is invalid or not recognized. | Provide a valid review decision: `approve`, `changes_requested`, or `reject`. |
| `BLOCKED-P6-PREREQUISITES-NOT-MET` | P6 prerequisites not satisfied: P5 approval, P5.3 pass, P5.5 approval, P5.4/P5.6 compliance missing. | Complete all prerequisite gates before entering Phase 6 Implementation QA. |

### 4.10 Other Codes

| Code | Description | Remediation |
|------|-------------|-------------|
| `BLOCKED-LEGACY-DECISION-PACK-FORMAT` | Decision-pack contains legacy interactive A/B prompt wording. | Normalize decision-pack to automatic policy wording and rerun persistence. |
| `BLOCKED-INVALID-NEXT-ACTION` | Response contract validation rejected `next_action` for current phase/gate. | Use `next_action.type=command` before phase 4 and rerun response rendering. |
| `BLOCKED-GOLDEN-BASELINE-MODIFIED-IN-PR` | Golden baseline files were modified in a PR, risking regression masking. | Revert baseline modifications or get explicit approval. |
| `BLOCKED-2-REPO-DISCOVERY` | Phase 2 (Repo Discovery) could not complete. | Ensure valid repo context and retry discovery. |
| `BLOCKED-R` | A recovery routine is required to proceed (explicit recovery gate). | Run `/continue` or the defined recovery routine and re-validate `SESSION_STATE`. |

### 4.11 Parameterized Prefixes

These codes accept a dynamic `:<key>` suffix at runtime:

| Prefix | Description |
|--------|-------------|
| `BLOCKED-MISSING-ADDON:<key>` | Specific addon identified by `<key>` is missing. |
| `BLOCKED-MISSING-RULEBOOK:<key>` | Specific rulebook identified by `<key>` is missing. |
| `BLOCKED-ADDON-CONFLICT:<key>` | Specific addon conflict identified by `<key>`. |

---

## 5. Known Issues

### 5.1 Orphan Codes

Three codes exist in `REASON_REMEDIATION_MAP.json` but are **not registered**
in the Python SSOT (`governance/domain/reason_codes.py`):

| Code | Status |
|------|--------|
| `BLOCKED-REPO-IDENTITY-MISMATCH` | Possibly superseded by `BLOCKED-FINGERPRINT-MISMATCH`. |
| `BLOCKED-GATE-FAILED` | Possibly superseded by specific P5.x/P6 gate codes. |
| `BLOCKED-PHASE-TRANSITION` | Possibly early-design or deprecated. |

These orphan codes will not be emitted by the current engine but retain
remediation data for backward compatibility.

### 5.2 Code String Irregularities

| Code | Issue |
|------|-------|
| `BLOCKED-R` | Unusually short — intentional shorthand for recovery gate. |
| `BLOCKED-2-REPO-DISCOVERY` | Numeric prefix (`2-`) — encodes Phase 2 origin. |

Both are registered in the Python SSOT and function correctly. The naming
is a product decision, not a defect.

---

## 6. Reference

### Authoritative Sources (SSOT)

| Artifact | Path |
|----------|------|
| Reason code constants | `governance/domain/reason_codes.py` |
| Reason code registry | `governance/assets/catalogs/reason_codes.registry.json` |
| Remediation map | `governance/assets/catalogs/REASON_REMEDIATION_MAP.json` |
| Blocked reason catalog | `governance/assets/reasons/blocked_reason_catalog.yaml` |
| Embedded reason registry | `governance/engine/_embedded_reason_registry.py` |

### Operator Scripts

| Script | Purpose |
|--------|---------|
| `scripts/validate_rulebook.py` | Validate profile rulebooks against schema |
| `scripts/governance_lint.py` | Structural + parity + version + hash checks |
| `scripts/migrate_rulebook_schema.py` | Schema migration with dry-run support |

### Related Documents

| Document | Path |
|----------|------|
| Security model | `docs/SECURITY_MODEL.md` |
| Governance invariants | `docs/governance_invariants.md` |
| Phase API | `governance/assets/phase_api.yaml` |
| Quickstart | `QUICKSTART.md` |

---

> SSOT: `governance/domain/reason_codes.py` is the only truth for reason code registration.
> Kernel: `governance/kernel/*` is the only control-plane implementation.
> MD files are AI rails/guidance only and are never routing-binding.
