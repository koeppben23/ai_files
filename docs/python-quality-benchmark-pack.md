# Python Quality Benchmark Pack

Date: 2026-02-11
Source: `diagnostics/PYTHON_QUALITY_BENCHMARK_PACK.json`
Profile target: `backend-python` + required addon `backendPythonTemplates`

## Goal

Provide a deterministic benchmark to evaluate backend-python business-code and
test-code quality under governance contracts, with evidence-backed scoring and
direct comparability over repeated runs.

## Included tasks (5)

1. service boundary refactor with deterministic seam
2. request/response contract evolution with compatibility checks
3. migration-safe persistence change with rollback/backout evidence
4. async reliability and failure-path test coverage
5. security/auth guard hardening with negative-path and log-safety evidence

## Run contract

- required baseline commands:
  - `${PYTHON_COMMAND} -m pytest -q`
  - `${PYTHON_COMMAND} scripts/governance_lint.py`
- no-claim-without-evidence applies:
  - missing/stale required claim evidence remains `NOT_VERIFIED`
- output contract:
  - default compact session snapshot
  - full diagnostics/state only on explicit intent

## Rubric

- criteria (weight=3 each):
  - business-boundary correctness
  - test determinism and coverage quality
  - evidence completeness/freshness
  - rollback and operational safety
  - security and logging hygiene
- thresholds:
  - pass ratio: `0.85`
  - high confidence: `0.90`
- hard invariant:
  - if one required claim lacks evidence, result is `NOT_VERIFIED` regardless of weighted ratio.

## Compare against Java track

- use identical run conditions (same repo state, same host constraints, same
  evidence freshness expectations)
- compare at least:
  - weighted ratio
  - `NOT_VERIFIED` incidence
  - blocker recovery quality (single primary action + one command)
  - re-run stability (delta/no-delta consistency)

## Usage

1. apply each benchmark task in isolation on a clean branch
2. run required commands and collect BuildEvidence IDs
3. score criteria and compute ratio
4. mark `NOT_VERIFIED` when required evidence is missing/stale
5. archive results with commit SHA and timestamp for reproducibility

Runner helper:

```bash
${PYTHON_COMMAND} scripts/run_quality_benchmark.py \
  --pack diagnostics/PYTHON_QUALITY_BENCHMARK_PACK.json \
  --observed-claim claim/tests-green \
  --observed-claim claim/static-clean \
  --observed-claim claim/no-drift \
  --criterion-score PYR-1=0.9 \
  --criterion-score PYR-2=0.9 \
  --criterion-score PYR-3=0.9 \
  --criterion-score PYR-4=0.9 \
  --criterion-score PYR-5=0.9 \
  --output diagnostics/benchmark-results/python-quality.json
```
