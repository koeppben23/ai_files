# End-to-End Phases

This document is the detailed phase map that was previously embedded in `README.md`.
If this file and `master.md` ever diverge, `master.md` is authoritative.

## Customer View (Short)

- Bootstrap validates install/path/session prerequisites before work proceeds.
- Discovery builds repo context and reusable decision artifacts.
- Planning produces an implementation path without bypassing gates.
- Gate reviews validate architecture, tests, business rules (when enabled), and rollback safety.
- Final QA issues a deterministic readiness decision (`ready-for-pr` or `fix-required`).

## Full Phase Map

| Phase | What it does (one-line) | Gate / blocked behavior |
| ----- | ------------------------ | ----------------------- |
| Phase 0 - Bootstrap (conditional) | Validates variable/path bootstrap when required before workflow execution. | If bootstrap evidence or variable resolution is invalid/missing, workflow is `BLOCKED` (fail-closed). |
| Phase 1 - Rules Loading | Loads rulebooks lazily in controlled order (bootstrap now, profile after discovery, core/templates/addons before planning). | Blocks if required rulebooks/evidence cannot be resolved for the current phase. |
| Phase 2 - Repository Discovery | Builds repo understanding (structure, stack, architecture signals, contract surface), with cache-assisted warm start when valid. | Non-gate phase, but missing required discovery artifacts can trigger `BLOCKED` continuation pointers. |
| Phase 2.1 - Decision Pack (default, non-gate) | Distills discovery outputs into reusable decisions/defaults for later phases. | Non-gate; if evidence is insufficient, decisions remain `not-verified` and downstream confidence is capped. |
| Phase 1.5 - Business Rules Discovery (optional) | Extracts business rules from code/ticket artifacts when activated or required. | Optional activation; once executed, Phase 5.4 becomes mandatory for code readiness. |
| Phase 3A - API Inventory | Inventories external API artifacts and interface landscape. | Non-gate validation stage; blocks only when required API evidence is missing for active scope. |
| Phase 3B-1 - API Logical Validation | Validates API specs for logical consistency at specification level. | Non-gate validation stage; unresolved spec issues can block progression to later contract-sensitive steps. |
| Phase 3B-2 - Contract Validation (Spec <-> Code) | Validates contract fidelity between specification and implementation. | Contract mismatches block readiness when contract gates are active/applicable. |
| Phase 4 - Ticket Execution (planning) | Produces the concrete implementation plan and review artifacts; no code output yet. | Planning phase; code-producing output remains blocked until explicit gate progression permits it. |
| Phase 5 - Lead Architect Review (gate) | Architecture gatekeeper review for feasibility, risk, and quality readiness. | Explicit gate; failure blocks progression to implementation readiness. |
| Phase 5.3 - Test Quality Review (critical gate) | Reviews test strategy/coverage quality against gate criteria. | Critical gate; must pass (or pass with governed exceptions) before PR readiness. |
| Phase 5.4 - Business Rules Compliance (conditional gate) | Checks implemented plan/output against extracted business rules. | Mandatory only if Phase 1.5 ran; non-compliance blocks readiness. |
| Phase 5.5 - Technical Debt Proposal (optional gate) | Reviews and decides technical debt proposals and mitigation posture. | Optional gate; when activated, unresolved debt decisions can block approval. |
| Phase 5.6 - Rollback Safety | Evaluates rollback/recovery safety for relevant changes (within Phase 5 family). | Required when rollback-sensitive changes exist; failed rollback safety blocks progression. |
| Phase 6 - Implementation QA (final gate) | Final quality assurance and release-readiness decision (`ready-for-pr` vs `fix-required`). | Final explicit gate; failed QA blocks PR readiness. |

## Phase-Coupled Persistence (Outside Repository)

| Phase | Artifact | Target | Write condition |
| ----- | -------- | ------ | --------------- |
| Phase 2 | `repo-cache.yaml` | `${REPO_CACHE_FILE}` (`[REPO-CACHE-FILE]`) | Written after successful discovery/cache refresh. |
| Phase 2 | `repo-map-digest.md` | `${REPO_DIGEST_FILE}` (`[REPO-MAP-DIGEST-FILE]`) | Written after successful digest generation. |
| Phase 2 | `workspace-memory.yaml` (observations/patterns) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Allowed for observational writeback when discovery evidence is sufficient. |
| Phase 2.1 | `decision-pack.md` | `${REPO_DECISION_PACK_FILE}` (`[DECISION-PACK-FILE]`) | Written when at least one decision/default is produced. |
| Phase 1.5 | `business-rules.md` | `${REPO_BUSINESS_RULES_FILE}` (`[BR-INVENTORY-FILE]`) | Written when Business Rules Discovery is executed. |
| Phase 5 (conditional) | `workspace-memory.yaml` (decisions/defaults) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Only when Phase 5 is approved and user confirms exactly: `Persist to workspace memory: YES`. |
