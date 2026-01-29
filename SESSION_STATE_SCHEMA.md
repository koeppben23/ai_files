# SESSION_STATE Schema (Canonical Contract)

This document defines the **canonical SESSION_STATE contract** used by `master.md` and `continue.md`.
It exists to prevent “session state drift” across models and sessions.

## 1. Required Keys (Minimum)

The following keys MUST exist once Phase 1 has completed successfully:

- `SESSION_STATE.ActiveProfile` (string)
- `SESSION_STATE.ProfileSource` (enum)
- `SESSION_STATE.ProfileEvidence` (string)
- `SESSION_STATE.ConfidenceLevel` (integer 0-100)
- `SESSION_STATE.Next` (string; phase pointer)

## 2. Profile Fields

### 2.1 ActiveProfile
String identifier, e.g.:
- `"backend-java"`
- `"frontend-angular-nx"`

### 2.2 ProfileSource (enum)
- `user-explicit`
- `auto-detected-single`
- `repo-fallback`
- `component-scope-inferred`
- `ambiguous` (only allowed when BLOCKED)

### 2.3 ProfileEvidence
Human-readable evidence string (paths/files), e.g.:
- `"~/.config/opencode/rules/profiles/rules.backend-java.md"`
- `"pom.xml, src/main/java"`
- `"apps/web, nx.json"`

## 3. Component Scope (Monorepos / Bounded Ownership)

Optional but strongly recommended for monorepos:

- `SESSION_STATE.ComponentScopePaths` (array of repo-relative paths)
- `SESSION_STATE.ComponentScopeSource` (enum: `user-explicit` | `assistant-proposed`)
- `SESSION_STATE.ComponentScopeEvidence` (string)

Invariant:
- If `ComponentScopePaths` is set, profile detection and recommendations MUST prefer signals inside those paths.

## 4. Repository Model (Phase 2+)

Once Phase 2 (Repository Discovery) completes, the following keys SHOULD exist and are strongly recommended for efficiency and determinism:

- `SESSION_STATE.RepoMapDigest` (object; compact system model)
  - recommended subkeys: `EntryPoints`, `Modules`/`Boundaries`, `DataStores`, `IntegrationPoints`, `CrossCutting`
- `SESSION_STATE.DecisionDrivers` (array of strings or structured entries; each SHOULD include evidence)
- `SESSION_STATE.WorkingSet` (array; repo-relative paths with rationale)
- `SESSION_STATE.TouchedSurface` (object; planned/actual surface area)
  - recommended subkeys:
    - `FilesPlanned` (array)
    - `ContractsPlanned` (array)
    - `SchemaPlanned` (array)
    - `SecuritySensitive` (boolean)
- `SESSION_STATE.FastPath` (boolean; optional)
- `SESSION_STATE.FastPathReason` (string; optional)

Invariant:
- If `WorkingSet` exists, subsequent phases SHOULD ground planning/review in it unless evidence requires expansion.

## 5. ConfidenceLevel

Integer 0–100.

Invariant:
- If `ConfidenceLevel < 70`, the system MUST not proceed past gates that require approvals.

## 6. Next (Phase Pointer)

String describing the next executable step, e.g.:
- `"Phase2-RepoDiscovery"`
- `"Phase4-TicketExecution"`
- `"Phase5-ArchitectureGate"`

Invariant:
- `continue.md` MUST execute ONLY the step referenced by `SESSION_STATE.Next`.

Additional invariants:
- `SESSION_STATE.Next` MUST NOT skip mandatory gates implied by the Master Prompt and loaded rulebooks.
  Example: if `SESSION_STATE.Gates.P5-Architecture != approved`, `Next` MUST NOT point to a code-producing step.
- If `SESSION_STATE.Mode = BLOCKED`, `Next` MUST start with `BLOCKED-` and describe the minimal missing input.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE - SESSION_STATE_SCHEMA.md
