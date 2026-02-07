# Risk Tiering Shared Rulebook

This document defines canonical risk-tiering semantics used by multiple profiles/addons.
It is designed as an advisory addon rulebook.

## Intent (binding)

Standardize risk-tier classification so evidence depth and gate strictness remain deterministic across rulebooks.

## Scope (binding)

Tier classification (`TIER-LOW|TIER-MEDIUM|TIER-HIGH`), tier evidence minimums, and unresolved-tier handling.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
As a shared advisory addon, this rulebook refines risk evidence behavior and MUST NOT override master/core/profile constraints.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/riskTiering.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 2/2.1: determine and justify active risk tier.
- Phase 5: enforce tier-specific evidence minimums in gate decisions.
- Phase 6: ensure unresolved tier gaps are reported as `not-verified` with recovery.

## Evidence contract (binding)

- Maintain `SESSION_STATE.AddonsEvidence.riskTiering.status` (`loaded|skipped|missing-rulebook`).
- Advisory warnings use `WARN-*` codes and recovery actions, not addon-only hard blocks.

## Tooling (recommended)

- Use repo-native verification commands appropriate to the selected tier and record evidence refs.
- If tier evidence commands cannot run, emit WARN + recovery and keep affected claims `not-verified`.

---

## Principal Hardening v2.1 - Standard Risk Tiering (Binding)

### RTN-1 Canonical tiers (binding)

All addon/template assessments MUST use this canonical tier syntax:

- `TIER-LOW`: local/internal changes with low blast radius and no external contract or persistence risk.
- `TIER-MEDIUM`: behavior changes with user-facing, API-facing, or multi-module impact.
- `TIER-HIGH`: contract, persistence/migration, messaging/async, security, or rollback-sensitive changes.

If uncertain, choose the higher tier.

### RTN-2 Tier evidence minimums (binding)

- `TIER-LOW`: build/lint (if present) + targeted changed-scope tests.
- `TIER-MEDIUM`: `TIER-LOW` evidence + at least one negative-path assertion for changed behavior.
- `TIER-HIGH`: `TIER-MEDIUM` evidence + one deterministic resilience/rollback-oriented proof
  (retry/idempotency/recovery/concurrency as applicable).

### RTN-3 Tier-based gate decisions (binding)

- A gate result cannot be `pass` when mandatory tier evidence is missing.
- For advisory addons, missing tier evidence remains non-blocking but MUST emit WARN + recovery and result `partial` or `fail`.
- For required addons/templates, missing `TIER-HIGH` evidence may block code-phase per master/core/profile policy.

### RTN-4 Required SESSION_STATE shape (binding)

```yaml
SESSION_STATE:
  RiskTiering:
    ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH
    Rationale: "short evidence-based reason"
    MandatoryEvidence:
      - EV-001
      - EV-002
    MissingEvidence: []
```

### RTN-5 Unresolved tier handling (binding)

If tier cannot be determined from available evidence, set status code `WARN-RISK-TIER-UNRESOLVED`,
provide a conservative default (`TIER-HIGH`), and include recovery steps to refine classification.

---

## Examples (GOOD/BAD)

GOOD:
- Change touches Kafka consumer idempotency + retry semantics -> classify `TIER-HIGH` with resilience evidence.

BAD:
- Messaging/contract-impacting change labeled `TIER-LOW` to avoid additional verification.

GOOD:
- Pure internal refactor with unchanged behavior and no external contract impact -> `TIER-LOW` with targeted tests.

## Troubleshooting

1) Symptom: Tier cannot be resolved during planning
- Cause: touched surface or impact is under-specified
- Fix: default to `TIER-HIGH`, record `WARN-RISK-TIER-UNRESOLVED`, and request missing scope evidence.

2) Symptom: Gate remains partial despite green tests
- Cause: mandatory tier evidence set is incomplete
- Fix: add missing negative-path/resilience proof required for active tier.

3) Symptom: Tiering differs between addons
- Cause: inconsistent rationale or non-canonical tier labels
- Fix: normalize to `TIER-LOW|TIER-MEDIUM|TIER-HIGH` and document one shared rationale in SESSION_STATE.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
