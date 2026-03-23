# Governance Schemas

schema: governance.schemas.v1

## Response Envelope

schema: governance.response_envelope.v1

Reference:
- `governance_runtime/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json`

## Compact Mode (Presentation)

schema: governance.compact_mode.v1

```json
{
  "status": "<BLOCKED|WARN|OK|NOT_VERIFIED>",
  "phase": "<phase id>",
  "gate": "<active gate or none>",
  "next_action": "<single concrete next action>",
  "evidence_summary": "<one-line evidence summary>",
  "source_of_truth": "<kernel|ssot|schema ref>"
}
```

## Preflight Snapshot

schema: governance.preflight.v1

```json
{
  "observed_at": "<iso-8601>",
  "available": "<comma-separated commands or none>",
  "missing": "<comma-separated commands or none>",
  "impact": "<one concise sentence>",
  "next": "<single concrete next step>",
  "build_toolchain": {
    "DetectedTools": {"<tool>": "<version|null>"},
    "ObservedAt": "<iso-8601>"
  }
}
```

## Phase 4 Plan Record

schema: governance.phase4.plan.v1

```json
{
  "FeatureComplexity": {
    "Class": "SIMPLE-CRUD|REFACTORING|MODIFICATION|COMPLEX|STANDARD",
    "Reason": "<one line>",
    "PlanningDepth": "minimal|standard|full|maximum"
  },
  "MiniADR": {
    "Context": "<1-2 lines>",
    "Decision": "<1 line>",
    "Rationale": "<1 line>",
    "Consequences": "<1 line>",
    "Rollback": "<1 line>"
  },
  "TestStrategy": ["<short test plan line>"]
}
```

## Phase 5 Gate Record

schema: governance.phase5.gates.v1

```json
{
  "Gates": {
    "P5-Architecture": "architecture-approved|architecture-rejected",
    "P5.3-TestQuality": "pass|pass-with-exceptions|fail",
    "P5.4-BusinessRules": "compliant|compliant-with-exceptions|not-applicable|gap-detected",
    "P5.5-TechnicalDebt": "approved|not-applicable|rejected",
    "P5.6-RollbackSafety": "approved|not-applicable|rejected"
  }
}
```

## Phase 6 QA Record

schema: governance.phase6.qa.v1

```json
{
  "Gates": {
    "P6-ImplementationQA": "ready-for-pr|fix-required"
  },
  "BuildEvidence": {
    "status": "not-provided|partially-provided|provided-by-user|verified-by-tool",
    "CompileResult": "pass|fail|skipped",
    "TestResult": "pass|fail|skipped",
    "IterationsUsed": {"Compile": 0, "Test": 0}
  }
}
```
