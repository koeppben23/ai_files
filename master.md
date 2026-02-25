---
description: "Operator guidance for governance phases 1-6"
priority: highest
---

# Governance-Version: 2.0.0
# MASTER PROMPT

This document defines the highest-priority AI guidance for the governance workflow.

## Binding Authority

SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the authoritative source for routing, execution, and validation.
Kernel: `governance/kernel/*` is the authoritative control-plane implementation.
MD files are AI rails/guidance only and are never routing-binding.

## Global Principles

1. **Fail-Closed Mode**: The governance system operates in fail-closed mode. Missing evidence blocks progress.
2. **Evidence-Based**: No non-trivial claim without artifact-backed proof.
3. **Scope Lock**: The AI may only access artifacts provided in the current session scope.
4. **Repo-First**: All persistent artifacts must be stored outside the repo working tree.

## Priority Order

When rules conflict, the following order applies:

1. Master Prompt (this document)
2. `rules.md` (technical core rules)
3. Active profile rulebook (e.g., `rules_backend-java.md`)
4. Activated templates/addon rulebooks (manifest-driven)
5. Ticket specification
6. General model knowledge

> **Stability sync note (binding):** governance release/readiness decisions MUST also satisfy `STABILITY_SLA.md`.
> **Profile selection is kernel-enforced.**
Stability sync note (binding): governance release/readiness decisions MUST also satisfy `STABILITY_SLA.md`.
>
> `STABILITY_SLA.md` is the normative Go/No-Go contract for governance releases.

## 1. PRIORITY ORDER

## Execution Flow

The governance workflow proceeds through phases 1-6, with conditional branches (e.g., Phase 1.5, 2.1, 3A/3B).
Phase 1.3 is mandatory before any phase >= 2.

## Decision Memory

Non-trivial architectural decisions must be recorded as ADR entries in:
`${REPO_DECISIONS_FILE}`

ADR entries are mandatory for:
- New abstractions or architectural boundaries
- New domain concepts with behavior/invariants
- New persistence, communication, or contract strategies
- Major dependency/framework/tooling changes

## Thematic Rails

Detailed guidance for specific areas is available in thematic rails:

- **Planning**: `docs/governance/rails/planning.md`
- **Implementation**: `docs/governance/rails/implementation.md`
- **Testing**: `docs/governance/rails/testing.md`
- **PR Review**: `docs/governance/rails/pr_review.md`
- **Failure Handling**: `docs/governance/rails/failure_handling.md`

## Output Constraints

Output must remain concise. Maximum:
- 5 files per response
- 300 diff lines per response block

## Confidence & Gates

- Code production requires explicit gate approval (Phase 5 + P5.3)
- No code before Phase 5 approval
- Confidence < 70% -> DRAFT mode (no code production)

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
