# SESSION_STATE_SCHEMA.md

This document defines the **canonical, authoritative SESSION_STATE contract** used by `master.md`, `continue.md`, and `resume.md`.
It exists to prevent **session-state drift**, enforce **gates**, and guarantee **deterministic continuation** across models and sessions.

Normative language (MUST / SHOULD / MAY) is binding.

---

## 1. Purpose

`SESSION_STATE` captures the deterministic execution state of an AI‑governed workflow.
It exists to ensure:

- resumability without reinterpretation
- enforceable quality gates
- traceable architectural decisions
- bounded scope and evidence discipline
- reduced cognitive load for the user

---

## 2. Required Top‑Level Keys

Every `SESSION_STATE` object MUST include:

```yaml
SESSION_STATE:
  Phase: <enum>
  Mode: <enum>
  ConfidenceLevel: <0-100>
  Next: "<canonical-next-step>"
```

---

## 3. Phase (enum)

```yaml
Phase:
  - 1
  - 1.5
  - 2
  - 3A
  - 3B-1
  - 3B-2
  - 4
  - 5
  - 5.3
  - 5.4
  - 5.5
  - 6
```

---

## 4. Mode (enum)

```yaml
Mode:
  - NORMAL
  - DEGRADED
  - DRAFT
  - BLOCKED
```

**Invariants**
- If `Mode = BLOCKED`, `Next` MUST start with `BLOCKED-`.
- If `ConfidenceLevel < 70`, auto‑advance and code output are forbidden.

---

## 5. ConfidenceLevel

```yaml
ConfidenceLevel: 0-100
```

---

## 6. Profile Resolution

```yaml
Profile:
  Name: "<profile-name>"
  Source:
    - user-explicit
    - auto-detected-single
    - component-scope-filtered
    - repo-fallback
    - ambiguous
```

---

## 7. Scope & Change Surface

### 7.1 WorkingSet

```yaml
WorkingSet:
  - path: "<path>"
    rationale: "<why>"
```

### 7.2 TouchedSurface

```yaml
TouchedSurface:
  FilesPlanned: []
  ContractsPlanned: []
  SchemaPlanned: []
  SecuritySensitive: true | false
```

### 7.3 DependencyChanges

```yaml
DependencyChanges:
  Added: []
  Updated: []
  Removed: []
```

---

## 8. Gates

```yaml
Gates:
  P5-Architecture: pending | approved | rejected
  P5.3-TestQuality: pending | pass | pass-with-exceptions | fail
  P5.4-BusinessRules: pending | compliant | compliant-with-exceptions | gap-detected | not-applicable
  P5.5-TechnicalDebt: pending | approved | rejected | not-applicable
  P6-ImplementationQA: pending | ready-for-pr | fix-required
```

### 8.1 GateArtifacts

```yaml
GateArtifacts:
  <GateName>:
    Required: []
    Provided: {}
```

---

## 9. ArchitectureDecisions

```yaml
ArchitectureDecisions:
  - ID: "AD-YYYY-NNN"
    Status: proposed | approved
```

---

## 10. RollbackStrategy

```yaml
RollbackStrategy:
  Type: feature-flag | blue-green | canary | hotfix | none
```

---

## 11. CrossRepoImpact

```yaml
CrossRepoImpact:
  AffectedServices: []
  RequiredSyncPRs: []
```

---

## 12. Output Control

```yaml
OutputMode: normal | architect-only
DecisionSurface: {}
```

---

## 13. Ticket Record

```yaml
TicketRecordDigest: "<summary>"
DecisionPack: "<digest>"
```

---

## 14. BuildEvidence

```yaml
BuildEvidence:
  Status: not-provided | partially-provided | provided-by-user
```

---

## 15. Next Pointer

```yaml
Next: "<next-step>"
```

---

## 16. Global Invariants

- No gate may pass with missing artifacts.
- No code without gate approval.
- No reinterpretation on resume.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE - SESSION_STATE_SCHEMA.md
