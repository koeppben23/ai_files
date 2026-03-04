# Quality Benchmark Pack Matrix

Date: 2026-02-11

This matrix lists machine-readable benchmark packs for active governance profiles.

## Benchmark packs

- `governance/assets/catalogs/BACKEND_JAVA_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/PYTHON_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/FRONTEND_ANGULAR_NX_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/OPENAPI_CONTRACTS_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/CUCUMBER_BDD_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/POSTGRES_LIQUIBASE_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/FRONTEND_CYPRESS_TESTING_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/FRONTEND_OPENAPI_TS_CLIENT_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/DOCS_GOVERNANCE_QUALITY_BENCHMARK_PACK.json`
- `governance/assets/catalogs/FALLBACK_MINIMUM_QUALITY_BENCHMARK_PACK.json`

## Common contract

- Each pack includes:
  - profile target
  - deterministic task set
  - evidence/claim contract (`No claim without evidence`)
  - scoring rubric and thresholds
- Missing or stale required evidence must result in `NOT_VERIFIED` semantics.

## Usage

1. select profile benchmark pack
2. execute benchmark tasks on isolated branch
3. collect BuildEvidence IDs and claim mappings
4. score rubric with threshold checks
5. mark non-evidenced claims as `NOT_VERIFIED`
