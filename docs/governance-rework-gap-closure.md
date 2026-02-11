# Governance Rework Gap Closure

Date: 2026-02-11
Branch: `feat/governance-rework-gap-closure`
Base: `develop/governance-engine`

## Goal

Close the remaining system-level 9/10 -> 10/10 gaps identified after the
session-state rollout and evidence-backfeed milestones.

## Implemented Gap Closures

### 1) Migration tooling + backup before first canonical write

- Added deterministic migration tool: `scripts/migrate_session_state.py`
- Tool behavior:
  - creates `SESSION_STATE.json.backup` before first canonicalizing write
  - writes canonical fields through repository save path
  - machine-readable exit codes: `0=ok`, `2=blocked`
  - machine-readable JSON output payload for automation

### 2) Two-layer output/render contract modules

- Added `governance/render/` package:
  - `intent_router.py`
  - `delta_renderer.py`
  - `token_guard.py`
  - `render_contract.py`
- Enforces deterministic two-layer response shape and budget-trim order.

### 3) Evidence freshness / TTL strictness for claim verification

- Orchestrator claim backfeed now evaluates evidence freshness using
  `observed_at` and TTL policy.
- Added stale-evidence reason code:
  - `NOT_VERIFIED-EVIDENCE-STALE`
- Required claim evidence that is stale now yields deterministic
  `not_verified` status with stale evidence IDs.

### 4) Engine lifecycle / rollback E2E pointer contract

- Added lifecycle module: `governance/engine/lifecycle.py`
  - staged activation keeps rollbackable `previous` pointer
  - automatic rollback restores previous pointer and appends audit trail entry
  - rollback events include explicit `DEVIATION` audit payload

## Acceptance Evidence

Executed checks:

```bash
python3 -m pytest -q tests/test_migrate_session_state_script.py tests/test_render_contract.py tests/test_engine_lifecycle.py tests/test_engine_orchestrator.py tests/test_reason_code_registry.py
python3 -m pytest -q
python3 scripts/governance_lint.py
```

Results:

- targeted tests: `35 passed`
- full suite: `310 passed, 1 skipped`
- governance lint: `OK`
