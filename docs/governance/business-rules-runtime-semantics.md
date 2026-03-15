# Business Rules Runtime Semantics

Purpose: explain the current business-rules runtime vocabulary without changing the runtime contract.

## 1. Reason-Code Layers

Business-rules persistence now carries two related but different diagnostic layers.

### 1.1 Canonical reason codes

These are the machine-relevant codes that drive validation, coverage, persistence, and fail-closed behavior.

- Validation integrity:
  - `BUSINESS_RULES_RENDER_MISMATCH`
  - `BUSINESS_RULES_COUNT_MISMATCH`
  - `BUSINESS_RULES_SEGMENTATION_FAILED`
  - `BUSINESS_RULES_SOURCE_VIOLATION`
- Code-quality / coverage:
  - `BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT`
  - `BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT`
  - `BUSINESS_RULES_CODE_TOKEN_ARTIFACT`
  - `BUSINESS_RULES_CODE_TEMPLATE_OVERFIT`
  - `BUSINESS_RULES_CODE_TOKEN_ARTIFACT_SPIKE`

These are the codes that matter for fail-closed gating and for the final persisted snapshot.

### 1.2 Derived quality explanations

Coverage payloads also expose short explanatory strings such as:

- `validation_render_mismatch`
- `validation_count_mismatch`
- `validation_segmentation_failed`
- `validation_source_violation`

These are not canonical reason codes. They are human-readable quality explanations carried in
`quality_insufficiency_reasons` so operators can see why coverage was forced to `poor`.

Rule:

- Canonical reason codes remain the authoritative machine vocabulary.
- Derived quality explanations remain payload/status-facing explanations only.

### 1.3 Validation dominates coverage

If final validation reports any of the following codes, coverage must be forced fail-closed:

| Validation code | Coverage effect | Derived quality explanation |
|---|---|---|
| `BUSINESS_RULES_RENDER_MISMATCH` | `is_sufficient = false`, `coverage_quality_grade = poor` | `validation_render_mismatch` |
| `BUSINESS_RULES_COUNT_MISMATCH` | `is_sufficient = false`, `coverage_quality_grade = poor` | `validation_count_mismatch` |
| `BUSINESS_RULES_SEGMENTATION_FAILED` | `is_sufficient = false`, `coverage_quality_grade = poor` | `validation_segmentation_failed` |
| `BUSINESS_RULES_SOURCE_VIOLATION` | `is_sufficient = false`, `coverage_quality_grade = poor` | `validation_source_violation` |

## 2. Counter Semantics

The code-extraction counters are intentionally split into discovery, post-drop, and validation stages.

| Field | Meaning |
|---|---|
| `raw_candidate_count` | All discovery candidates before dropping and before final validation |
| `dropped_candidate_count` | Discovery candidates removed before validation |
| `candidate_count` | Post-drop candidates that enter validation |
| `validated_code_rule_count` | Post-validation candidates accepted as business-valid code rules |
| `invalid_code_candidate_count` | Post-validation candidates rejected during validation |

Required invariants:

- `raw_candidate_count = dropped_candidate_count + candidate_count`
- `candidate_count = validated_code_rule_count + invalid_code_candidate_count`

Implementation note:

- `artifact_ratio` is currently measured against `candidate_count` (post-drop candidates).
- Discovery-drop artifacts and validation-rejected artifacts are therefore visible as separate diagnostics rather than collapsed into one ratio.

## 3. Artifact Boundaries

Business-rules persistence relies on four distinct document roles.

| Document | Role | Allowed use |
|---|---|---|
| Config-root `SESSION_STATE.json` | Session pointer | Activation/routing only |
| Workspace `SESSION_STATE.json` | Materialized session state | Canonical session truth |
| `SESSION_STATE.BusinessRules` | Final business-rules snapshot | Canonical persisted BR block inside session state |
| `business-rules-status.md` / `code_extraction_report.json` | Derived artifacts | Rendered from the final BR snapshot |

Rules:

- A session pointer must never be hydrated or persisted as if it were workspace session state.
- Business-rules hydration and persistence operate on materialized workspace session state only.
- `business-rules-status.md` and `code_extraction_report.json` must describe the same final snapshot truth as `SESSION_STATE.BusinessRules`.

## 4. Practical Review Checklist

When reviewing a business-rules change, verify:

- canonical reason codes still drive fail-closed behavior
- derived quality explanations are explanatory only
- the two counter equations still hold everywhere
- pointer, session state, and business-rules snapshot remain type-separated
- `ReportSha` matches across session snapshot, status file, and code extraction report
