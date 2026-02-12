# Quality Benchmarks

This document is the short benchmark landing page moved out of `README.md`.

## Purpose

Benchmark packs provide deterministic scoring for business-code and test-code quality across active profiles.

Pack files live under `diagnostics/*_QUALITY_BENCHMARK_PACK.json`.

## Quick Run Flow

1. Select a pack from [`quality-benchmark-pack-matrix.md`](quality-benchmark-pack-matrix.md).
2. Execute benchmark tasks on an isolated branch.
3. Collect required evidence artifacts and run scoring.
4. Apply "no claim without evidence" strictly (`PASS`/`FAIL`/`NOT_VERIFIED`).

Optional helper command:

```bash
python3 scripts/run_quality_benchmark.py --pack diagnostics/PYTHON_QUALITY_BENCHMARK_PACK.json
```

## References

- Python benchmark runbook: [`python-quality-benchmark-pack.md`](python-quality-benchmark-pack.md)
- Benchmark pack matrix: [`quality-benchmark-pack-matrix.md`](quality-benchmark-pack-matrix.md)
- Pipeline role template: [`governance-pipeline-roles-template.md`](governance-pipeline-roles-template.md)
