# SESSION_STATE Schema (Canonical Contract)

This document defines the **canonical SESSION_STATE contract** used by `master.md`, `continue.md`, and `resume.md`.
It exists to prevent **session state drift** across models and sessions.

---

## 1. Output Modes (MIN vs FULL)

The assistant MUST output `SESSION_STATE` in every response that advances or evaluates the workflow.

Two output modes are allowed:

- **MIN** (default): small, stable, continuation-critical fields only.
- **FULL** (expanded): includes discovery digests, working sets, decision packs, etc.

### 1.1 Default

- Default output mode is **MIN**.
- FULL is allowed only when required (see below) or explicitly requested.

### 1.2 When FULL is REQUIRED

The assistant MUST output **FULL** if any of these apply:

1) The current step is an **explicit gate** (Phase 5 / 5.3 / 5.4 / 5.5 / 6).
2) `SESSION_STATE.Mode = BLOCKED`.
3) A reviewer/audit request requires it (e.g., “show full session state”).
4) Phase 2 just completed (repo discovery) and this is the first time `RepoMapDigest` is produced.

### 1.3 Size constraint (recommended)

- MIN SHOULD be kept below ~40 lines.
- FULL SHOULD remain compact and prefer digests over full enumerations.

---

## 2. Required Keys (Phase 1+)

Once Phase 1 (rules loading) completes successfully, these keys MUST exist:

- `SESSION_STATE.Phase` (enum; see Section 3)
- `SESSION_STATE.Mode` (enum; see Section 4)
- `SESSION_STATE.ConfidenceLevel` (integer 0–100)
- `SESSION_STATE.Next` (string; canonical continuation pointer)
- `SESSION_STATE.LoadedRulebooks.core` (string path)
- `SESSION_STATE.LoadedRulebooks.profile` (string path or `""` if planning-only)
- `SESSION_STATE.ActiveProfile` (string)
- `SESSION_STATE.ProfileSource` (enum)
- `SESSION_STATE.ProfileEvidence` (string)
- `SESSION_STATE.Gates` (object; see Section 8)
- `SESSION_STATE.Risks` (array)
- `SESSION_STATE.Blockers` (array)
- `SESSION_STATE.Warnings` (array)

Invariant:
- If `Mode = BLOCKED`, `Next` MUST start with `BLOCKED-` and describe the minimal missing input.

---

## 3. Phase (enum)

Allowed values:

- `1` (rules loading)
- `2` (repository discovery)
- `1.5` (business rules discovery)
- `3A` (API inventory)
- `3B-1` (API logical validation)
- `3B-2` (contract validation spec ↔ code)
- `4` (ticket execution / plan)
- `5` (architecture gate)
- `5.3` (test quality gate)
- `5.4` (business rules compliance gate)
- `5.5` (technical debt gate)
- `6` (implementation QA gate)

---

## 4. Mode (enum)

Allowed values:

- `NORMAL`
- `DEGRADED`
- `DRAFT`
- `BLOCKED`

Invariant:
- If `ConfidenceLevel < 70`, auto-advance is forbidden and code-producing output is forbidden.

---

## 5. Profile Fields

### 5.1 ActiveProfile

String identifier, e.g.:
- `backend-java`
- `frontend-angular-nx`

### 5.2 ProfileSource (enum)

- `user-explicit`
- `auto-detected-single`
- `repo-fallback`
- `component-scope-inferred`
- `ambiguous` (only allowed when `Mode = BLOCKED`)

### 5.3 ProfileEvidence

Human-readable evidence string (paths/files), e.g.:
- `~/.config/opencode/rules/profiles/rules.backend-java.md`
- `pom.xml, src/main/java`
- `apps/web, nx.json`

---

## 6. Component Scope (Monorepos / Bounded Ownership)

Optional but strongly recommended for monorepos:

- `SESSION_STATE.ComponentScopePaths` (array of repo-relative paths)
- `SESSION_STATE.ComponentScopeSource` (enum: `user-explicit` | `assistant-proposed`)
- `SESSION_STATE.ComponentScopeEvidence` (string)

Invariant:
- If `ComponentScopePaths` is set, profile detection, discovery summaries, and recommendations MUST prefer signals inside those paths.

---

## 7. Repository Understanding (Phase 2+)

After Phase 2 completes, the session SHOULD include the following (required unless explicitly impossible due to missing repo access):

- `SESSION_STATE.RepoMapDigest` (object; compact repo understanding)
- `SESSION_STATE.DecisionDrivers` (array; each SHOULD include evidence)
- `SESSION_STATE.WorkingSet` (array; repo-relative paths + rationale)
- `SESSION_STATE.TouchedSurface` (object; planned/actual surface area)

### 7.1 RepoMapDigest (canonical)

`RepoMapDigest` is the canonical repo model.
Recommended subkeys:
- `Modules` / `Boundaries`
- `EntryPoints`
- `DataStores`
- `IntegrationPoints`
- `BuildAndTooling`
- `Testing`
- `ArchitecturalInvariants`
- `Hotspots`

### 7.2 Legacy alias (allowed)

- `SESSION_STATE.RepoModel` may exist as a legacy alias.
- If both exist, `RepoMapDigest` wins.

### 7.3 TouchedSurface (recommended structure)

- `FilesPlanned` (array)
- `ContractsPlanned` (array)
- `SchemaPlanned` (array)
- `SecuritySensitive` (boolean)

Invariant:
- If `WorkingSet` exists, subsequent planning/review MUST be grounded in it unless evidence requires expansion.

---

## 8. Gates (Phase 1+)

`SESSION_STATE.Gates` MUST exist after Phase 1 and include these keys:

- `P5-Architecture`: `pending | approved | rejected`
- `P5.3-TestQuality`: `pending | pass | pass-with-exceptions | fail`
- `P5.4-BusinessRules`: `pending | compliant | compliant-with-exceptions | gap-detected | not-applicable`
- `P5.5-TechnicalDebt`: `pending | approved | rejected | not-applicable`
- `P6-ImplementationQA`: `pending | ready-for-pr | fix-required`

Invariant:
- `Next` MUST NOT point to any code-producing step unless the relevant upstream gates are in an allowed state per `master.md` and `rules.md`.

---

## 9. Next (Phase Pointer)

`SESSION_STATE.Next` is a string describing the next executable step, e.g.:
- `Phase2-RepoDiscovery`
- `Phase2.1-DecisionPack`
- `Phase4-TicketExecution`
- `Phase5-ArchitectureGate`

Invariants:
- `Next` MUST NOT skip mandatory gates.

---

## 10. Decision Pack (Phase 2+; recommended)

To reduce cognitive load, Phase 2 SHOULD produce a compact **Decision Pack**.
If produced:

- `SESSION_STATE.DecisionPack` (array)
  - each entry SHOULD include: `id`, `decision`, `options`, `recommendation`, `evidence`, `what_changes_it`

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE - SESSION_STATE_SCHEMA.md
