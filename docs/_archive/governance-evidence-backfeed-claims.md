# Governance Evidence Backfeed Claims Contract

Date: 2026-02-11
Branch: `feat/governance-evidence-backfeed-claims`
Base: `develop/governance-engine`

## Goal

Strengthen the "no claim without evidence" contract by deriving quality claim
evidence directly from `SESSION_STATE.BuildEvidence` in orchestrator checks.

## Implemented Behavior

- `run_engine_orchestrator(...)` now supports claim evidence backfeed inputs:
  - `required_claim_evidence_ids`: claim evidence IDs that must be present
  - `session_state_document`: source document for claim evidence extraction

- Verified claim evidence is extracted from `SESSION_STATE.BuildEvidence`:
  - `claims_verified[]` entries
  - `items[]` entries with pass/verified status using `evidence_id`/`claim_id`
  - fallback canonicalization from `items[].claim` labels to `claim/<slug>`

- Missing claim evidence contributes to `missing_evidence` and preserves
  deterministic `NOT_VERIFIED-MISSING-EVIDENCE` behavior.

## Acceptance Evidence

Executed checks:

```bash
${PYTHON_COMMAND} -m pytest -q tests/test_engine_orchestrator.py tests/test_engine_e2e_matrix.py
${PYTHON_COMMAND} -m pytest -q
${PYTHON_COMMAND} scripts/governance_lint.py
```
