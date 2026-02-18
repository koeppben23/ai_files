# Quality Index (Spitzenniveau)

Purpose:
This document provides a single canonical entry point for defining
"top-tier" engineering output within this governance system.
It introduces no new rules and does not override existing ones.

## Canonical definition
A change qualifies as top-tier only if ALL of the following are true:

1. Governance gates are satisfied
   (see: master.md phases; SESSION_STATE_SCHEMA.md -> Gates.*).
2. Reasoning and decisions are evidence-bounded
   (see: SCOPE-AND-CONTEXT.md; SESSION_STATE_SCHEMA.md Evidence fields).
3. Repository-local standards are respected when present
   (e.g. AGENTS.md, CONTRIBUTING, CI rules).
4. Architectural decisions are explicit when architecture is affected
   (see: ADR.md; master.md decision points; active profile rules).
5. Verification depth is proportional to risk and change scope
   (see: active profiles; repo-local testing standards).
6. Portability and storage rules are followed for any persisted data
   (see: rules.md storage/path rules).
7. No unresolved conflicts with higher-priority governance sources exist
   (see: CONFLICT_RESOLUTION.md).

## Evidence checklist
For any non-trivial change, evidence SHOULD exist for:
- Scope and intent
- Decision rationale (alternatives + trade-offs)
- Verification performed (or justified omission)
- Risk and rollback considerations

## Usage
- Must be considered before declaring work "done".
- Must be satisfied before Phase 5 code emission in strict workflows.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# End of file — QUALITY_INDEX.md
