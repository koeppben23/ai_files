# SESSION_STATE_SCHEMA.md (Canonical Contract)

This document defines the **canonical SESSION_STATE contract** used by `master.md`, `continue.md`, and `resume.md`.
It exists to prevent **session state drift** across models and sessions and to make gates **enforceable**.

Normative language (MUST / SHOULD / MAY) is binding.

---

## 1. Output Modes (MIN vs FULL)

The assistant MUST output `SESSION_STATE` in every response that advances or evaluates the workflow.

Two output modes are allowed:

- **MIN** (default): small, stable, continuation-critical fields only.
- **FULL** (expanded): includes discovery digests, working sets, decision packs, gate artifacts, etc.

### 1.1 Default

- Default output mode is **MIN**.
- FULL is allowed only when required (see below) or explicitly requested.

### 1.2 When FULL is REQUIRED

The assistant MUST output **FULL** if any of these apply:

1) The current step is an **explicit gate** (Phase 5 / 5.3 / 5.4 / 5.5 / 6).
2) `SESSION_STATE.Mode = BLOCKED`.
3) A reviewer/audit request requires it (e.g., “show full session state”).
4) Phase 2 just completed (repo discovery) and this is the first time `RepoMapDigest` is produced.
5) `SESSION_STATE.ConfidenceLevel < 70` (DRAFT/BLOCKED; expanded state required to resolve ambiguity safely).

### 1.3 Size constraint (recommended)

- MIN SHOULD be kept below ~40 lines.
- FULL SHOULD remain compact and prefer digests over full enumerations.

---

## 2. Required Keys (Phase 1+)

Once Phase 1.1 (bootstrap) completes successfully, these keys MUST exist:

- `SESSION_STATE.Phase` (enum; see Section 3)
- `SESSION_STATE.Mode` (enum; see Section 4)
- `SESSION_STATE.ConfidenceLevel` (integer 0–100)
- `SESSION_STATE.Next` (string; canonical continuation pointer)
- `SESSION_STATE.LoadedRulebooks.core` (string path OR `""` if deferred until Phase 4)
- `SESSION_STATE.LoadedRulebooks.profile` (string path OR `""` if deferred/planning-only)
- `SESSION_STATE.ActiveProfile` (string OR `""` if deferred until post-Phase-2)
- `SESSION_STATE.ProfileSource` (enum; see Section 5)
- `SESSION_STATE.ProfileEvidence` (string)
- `SESSION_STATE.Gates` (object; see Section 8)

### Lazy-loading invariants (binding)

- Until Phase 2 completes:
  - ActiveProfile MAY be ""
  - ProfileSource MUST be "deferred"
  - LoadedRulebooks.profile MAY be ""

- Until Phase 4 begins:
  - LoadedRulebooks.core MAY be ""

- If Phase 4 begins and LoadedRulebooks.core is still "":
  → WORKFLOW MUST BE BLOCKED

**Invariant**
- If `Mode = BLOCKED`, `Next` MUST start with `BLOCKED-` and describe the minimal missing input.

---

## 3. Phase (enum)

Allowed values:

- `1` (rules loading)
- `1.1-Bootstrap` (minimal bootstrap / initial rule loading)
- `1.2-ProfileDetection` (profile detection after repo discovery)
- `1.3-CoreRulesActivation` (core rules activation at Phase 4 entry)
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

**Invariants**
- If `ConfidenceLevel < 70`, auto-advance is forbidden and code-producing output is forbidden.
- If `Mode = BLOCKED`, `Next` MUST start with `BLOCKED-` and the session MUST name the minimal unblock requirement.

Recommended calibration (rubric; clamp 0–100):
- +25 if `ActiveProfile` is unambiguous and evidenced
- +25 if `RepoMapDigest` exists and is evidence-backed (paths/files)
- +15 if `WorkingSet` exists and matches the plan
- +15 if `TouchedSurface` exists and matches planned/actual changes
- +10 if `BuildEvidence.status` is `partially-provided` or `provided-by-user` for relevant claims
- -20 if monorepo component scope is unclear or profile selection is ambiguous
- -15 if required artifacts for the current phase are missing (e.g., gates, digest)
- -15 if repository signals conflict (e.g., mixed build systems) and not resolved

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
- `deferred`
- `component-scope-inferred`
- `component-scope-filtered`
- `ambiguous` (**only allowed when `Mode = BLOCKED`**)

### 5.3 ProfileEvidence

Human-readable evidence string (paths/files), e.g.:
- `profiles/rules.backend-java.md`
- `${OPENCODE_HOME}/rules/profiles/rules.backend-java.md` (if installed globally)
- `pom.xml, src/main/java`
- `apps/web, nx.json`

**Invariant**
- After `ActiveProfile` is first set (post Phase 2 / Phase 1.2), it MUST remain stable unless the user explicitly changes it.
  If it changes, the workflow MUST return to Phase 1 to re-load rulebooks and re-evaluate gates.

---

## 6. Component Scope (Monorepos / Bounded Ownership)

Optional but strongly recommended for monorepos:

- `SESSION_STATE.ComponentScopePaths` (array of repo-relative paths)
- `SESSION_STATE.ComponentScopeSource` (enum: `user-explicit` | `assistant-proposed`)
- `SESSION_STATE.ComponentScopeEvidence` (string)

**Invariant**
- If `ComponentScopePaths` is set, profile detection, discovery summaries, and recommendations MUST prefer signals inside those paths.

---

## 7. Repository Understanding (Phase 2+)

After Phase 2 completes, the session SHOULD include the following (required unless explicitly impossible due to missing repo access):

- `SESSION_STATE.RepoMapDigest` (object; compact repo understanding)
- `SESSION_STATE.DecisionDrivers` (array; each SHOULD include evidence)
- `SESSION_STATE.WorkingSet` (array; repo-relative paths + rationale)
- `SESSION_STATE.TouchedSurface` (object; planned/actual surface area)

### 7.x Repo Cache File (OpenCode-only, recommended)

To speed up repeated `/master` sessions on the same repository, the workflow MAY use a structured repo cache file.
If used, the assistant SHOULD populate:

- `SESSION_STATE.RepoCacheFile` (object)

Recommended structure:

```yaml
SESSION_STATE:
  RepoCacheFile:
    SourcePath: "<path expression>"      # e.g., ${REPO_HOME}/repo-cache.yaml
    TargetPath: "<path expression>"      # same as SourcePath when writing
    Loaded: true | false
    Valid: true | false
    InvalidationReason: "<short text>"  # empty when Valid=true
    GitHead: "<sha|unknown>"
    RepoSignature: "<sha|unknown>"
    GitHeadMatch: true | false | unknown
    RepoSignatureMatch: true | false | unknown
    LastUpdated: "<YYYY-MM-DD|unknown>"
    FileStatus: written | write-requested | not-applicable
```

Binding rules:
- `RepoCacheFile.Valid = true` ONLY if cache validation rules in `master.md` are satisfied.
- If `RepoCacheFile.Valid = true`, Phase 2 discovery MAY be reduced or skipped (Fast Path), but gates MUST NOT be bypassed.
- If `RepoCacheFile.Valid = false`, the assistant MUST proceed with normal discovery and MUST regenerate the cache after Phase 2.

### 7.1 RepoMapDigest (canonical)

`RepoMapDigest` is the canonical repo model.
Recommended subkeys:
- `Modules` / `Boundaries`
- `EntryPoints`
- `DataStores`
- `IntegrationPoints`
- `BuildAndTooling`
- `Testing`
- `ConventionsDigest`
- `ArchitecturalInvariants`
- `Hotspots`

#### 7.1.a ConventionsDigest (recommended)

`ConventionsDigest` captures repo-native engineering conventions that materially impact code review outcomes.
It SHOULD be a short list (5–10 bullets), and each bullet SHOULD include evidence pointers (paths/symbols),
so subsequent planning/code generation can stay repo-consistent.

Recommended content (repo-driven):
- error handling & exception mapping conventions
- logging / correlation-id patterns
- transaction boundaries / retries / idempotency patterns (if applicable)
- DTO/mapping strategy (MapStruct/manual) and package placement
- testing conventions (naming, assertions, mocking policy, test-data builders)
- time/randomness determinism conventions (Clock injection, seeding)

Recommended structure:

```yaml
SESSION_STATE:
  RepoMapDigest:
    ConventionsDigest:
      - "<convention> (evidence: path/to/file or symbol)"
      - "<convention> (evidence: ...)"
```

### 7.2 Legacy alias (allowed)

- `SESSION_STATE.RepoModel` may exist as a legacy alias.
- If both exist, `RepoMapDigest` wins.

### 7.3 TouchedSurface (recommended structure)

- `FilesPlanned` (array)
- `ContractsPlanned` (array)
- `SchemaPlanned` (array)
- `SecuritySensitive` (boolean)

**Invariant**
- If `WorkingSet` exists, subsequent planning/review MUST be grounded in it unless evidence requires expansion.

#### 7.3.a Fast Path Evaluation (optional, efficiency-only)

Fast Path is an efficiency optimization, not a correctness shortcut.

If the assistant evaluates Fast Path, it SHOULD populate:
- `SESSION_STATE.FastPathEvaluation` (object)

Legacy compatibility:
- `SESSION_STATE.FastPath` (boolean) and `SESSION_STATE.FastPathReason` MAY exist.
- If `FastPathEvaluation.Eligible` exists, it is the canonical source of truth.

Recommended structure:

```yaml
SESSION_STATE:
  FastPath: false            # boolean; true only if Applied=true
  FastPathReason: ""         # legacy optional; keep short
  FastPathEvaluation:
    Evaluated: true               # boolean
    Eligible: false               # boolean (safe-to-apply)
    Applied: false                # boolean (actually used)
    Reason: "<short, evidence-backed>"
    Preconditions:
      RepoMapDigestLoaded: true | false
      PersistedGitHead: "<sha|unknown>"
      CurrentGitHead: "<sha|unknown>"
      GitHeadMatch: true | false | unknown
      PersistedRepoSignature: "<sha|unknown>"
      CurrentRepoSignature: "<sha|unknown>"
      RepoSignatureMatch: true | false | unknown
      TicketRiskClass: low | medium | high | unknown
    DenyReasons:                  # list, empty if Eligible=true
      - "<why fast path is not safe>"
    ReducedDiscoveryScope:        # only when Applied=true
      PathsScanned:
        - "<repo-relative path>"
      Skipped:
        - "<what was intentionally skipped>"
    EvidenceRefs:
      - "<paths/commands used to compute signatures>"
```

### 7.4 Dependency Changes (Supply Chain)

If the plan or implementation adds/updates/removes dependencies, the session SHOULD include:

- `SESSION_STATE.DependencyChanges` (object)

Recommended structure:

```yaml
SESSION_STATE:
  DependencyChanges:
    Added:
      - name: "<package>"
        version: "<version>"
        justification: "<why needed>"
        securityNotes: "<CVE/licensing notes or 'none'>"
        risk: low | medium | high
    Updated:
      - name: "<package>"
        from: "<old>"
        to: "<new>"
        reason: "<why>"
        securityNotes: "<CVE/licensing notes or 'none'>"
        risk: low | medium | high
    Removed:
      - name: "<package>"
        version: "<version or old>"
        reason: "<why removed>"
```

**Binding rules**
- If any dependency change is planned or observed, `DependencyChanges` MUST be present in FULL mode for Phases 4–6.
- If `DependencyChanges.Added` or `Updated` is non-empty, Phase 5 security sanity checks MUST explicitly include a dependency-risk line item.

---

## 8. Gates (Phase 1+)

`SESSION_STATE.Gates` MUST exist after Phase 1 and include these keys:

- `P5-Architecture`: `pending | approved | rejected`
- `P5.3-TestQuality`: `pending | pass | pass-with-exceptions | fail`
- `P5.4-BusinessRules`: `pending | compliant | compliant-with-exceptions | gap-detected | not-applicable`
- `P5.5-TechnicalDebt`: `pending | approved | rejected | not-applicable`
- `P5.6-RollbackSafety`: `pending | approved | rejected | not-applicable`
- `P6-ImplementationQA`: `pending | ready-for-pr | fix-required`

**Invariant**
- `Next` MUST NOT point to any code-producing step unless the relevant upstream gates are in an allowed state per `master.md` and `rules.md`.

### 8.1 Gate Artifacts (Enforcement Contract)

To make gates **objectively checkable** (not just narrative), the session MUST track required artifacts per gate in FULL mode at explicit gates.

Recommended structure:

```yaml
SESSION_STATE:
  GateArtifacts:
    P5-Architecture:
      Required: ["ArchitectureDecisions", "DecisionDrivers", "TouchedSurface"]
      Provided:
        ArchitectureDecisions: present | missing | not-applicable
        DecisionDrivers: present | missing | not-applicable
        TouchedSurface: present | missing | not-applicable
```

**Binding rules**
- When evaluating any explicit gate (Phase 5 / 5.3 / 5.4 / 5.5 / 5.6 / 6) and FULL output is required, `GateArtifacts` MUST include the current gate key with:
  - `Required` (list), and
  - `Provided` (status per required artifact).
- Allowed values for `Provided[*]` are: `present` | `missing` | `not-applicable`.
- If any `Provided` item is `missing`, the gate MUST NOT be marked as passing/approved; the assistant MUST:
  - set `Mode = BLOCKED`, and
  - set `Next` to a `BLOCKED-...` pointer describing the minimal missing artifact(s).

---

## 9. Architecture Decisions (Phase 5+)

To keep architecture reasoning **first-class and comparable across tickets**, the session MUST include:

- `SESSION_STATE.ArchitectureDecisions` (array) at the point `P5-Architecture` is approved.

Recommended structure:

```yaml
SESSION_STATE:
  ArchitectureDecisions:
    - ID: "AD-2026-001"
      Context: ["<what changed + why>"]
      Decision: ["<chosen approach>"]
      AlternativesRejected: ["<rejected option + brief why>"]
      Consequences: ["+ <benefit>", "- <cost/risk>"]
      EvidenceRefs: ["<paths or artifacts used>"]
      Status: proposed | approved
```

**Binding rules**
- When `Gates.P5-Architecture = approved`, `ArchitectureDecisions` MUST be non-empty and MUST contain at least one entry with `Status = approved`.
- If the assistant cannot produce a decision due to missing evidence, it MUST set `Mode = BLOCKED` and request the minimal missing inputs.

---

## 10. Rollback & Migration Strategy (Phase 4+)

For any change that impacts schema or externally-consumed contracts, the session MUST include:

- `SESSION_STATE.RollbackStrategy`

Recommended structure:

```yaml
SESSION_STATE:
  RollbackStrategy:
    Type: feature-flag | blue-green | canary | hotfix | none
    Steps: ["<how to rollback/revert safely>"]
    DataMigrationReversible: true | false
    Risk: low | medium | high
```

**Binding rules**
- If `TouchedSurface.SchemaPlanned` is non-empty OR `TouchedSurface.ContractsPlanned` is non-empty, `RollbackStrategy` MUST be present in FULL mode for Phases 4–6.
- If `DataMigrationReversible = false`, the plan MUST include explicit safety steps (backups, dual-write, shadow reads, etc.).

---

## 11. Cross-Repository / Consumer Impact (Microservices)

If the ticket changes an externally-consumed contract (OpenAPI, events, shared schema), the session SHOULD include:

- `SESSION_STATE.CrossRepoImpact`

Recommended structure:

```yaml
SESSION_STATE:
  CrossRepoImpact:
    AffectedServices:
      - name: "<service>"
        repository: "<repo identifier>"
        impactType: contract-change | api-version | event-schema
        breakingChange: true | false
    RequiredSyncPRs:
      - repository: "<repo identifier>"
        notes: "<what must be updated>"
```

**Binding rule**
- If `TouchedSurface.ContractsPlanned` is non-empty and the system cannot establish consumer impact, the assistant MUST set `Mode = BLOCKED` and request the minimal missing consumer inventory (or confirm “single-repo, no external consumers”).

---

## 12. OutputMode & Decision Surface (Cognitive Load Control)

### 12.x State Compression (token control for long sessions)

If a session becomes long (large RepoMapDigest / many iterations), the assistant MAY compress earlier discovery
details into a short summary while preserving decision-critical state.

Recommended structure:

```yaml
SESSION_STATE:
  StateCompression:
    Applied: true | false
    Compressed:
      - Phases: ["1", "2", "3A", "3B-1", "3B-2"]
        Summary: "<short summary of what was discovered>"
        Preserved: ["DecisionPack", "WorkingSet", "TouchedSurface", "Gates", "RollbackStrategy"]
```

To reduce user cognitive load, the session MAY include:

- `SESSION_STATE.OutputMode` (enum: `normal` | `architect-only`)
- `SESSION_STATE.DecisionSurface` (object)

Recommended structure:

```yaml
SESSION_STATE:
  OutputMode: architect-only
  DecisionSurface:
    MustDecideNow: ["<decision>"]
    CanDefer: ["<decision>"]
    AutoDecidedBySystem: ["<decision>"]
```

**Binding rules**
- If `OutputMode = architect-only`, `DecisionSurface` MUST be present and MUST contain the keys:
  - `MustDecideNow`, `CanDefer`, `AutoDecidedBySystem` (lists may be empty).
- In `architect-only` mode, responses MUST surface the DecisionSurface first; narrative text must be limited to rationale + evidence pointers.

---

## 13. Next (Phase Pointer)

`SESSION_STATE.Next` is a string describing the next executable step, e.g.:
- `Phase2-RepoDiscovery`
- `Phase2.1-DecisionPack`
- `Phase4-TicketExecution`
- `Phase5-ArchitectureGate`
- `BLOCKED-<reason>`

**Invariant**
- `Next` MUST NOT skip mandatory gates.

---

## 14. Decision Pack (Phase 2+; recommended)

To reduce cognitive load, Phase 2 SHOULD produce a compact **Decision Pack**.
If produced:

- `SESSION_STATE.DecisionPack` (array)
  - each entry SHOULD include: `id`, `decision`, `options`, `recommendation`, `evidence`, `what_changes_it`

---

## 15. Ticket Record (Phase 4+; required by rules)

When Phase 4 planning is produced, the workflow may include:
- `SESSION_STATE.TicketRecordDigest` (one-line summary)
- `SESSION_STATE.NFRChecklist` (object; may be elided in MIN if digest captures exceptions)

This is further specified as binding in `rules.md` (Ticket Record section).

---

## 16. Build Evidence

```yaml
BuildEvidence:
  status: not-provided | partially-provided | provided-by-user
  notes: "<what exists or is missing>"
  items:                # optional but strongly recommended; enables reviewer-proof verification
    - tool: "<maven|gradle|npm|spotbugs|checkstyle|archunit|openapi|pact|...>"
      command: "<exact command executed>"
      result: pass | fail | unknown
      scope: "<what this evidence covers (unit tests, integration tests, contract validation, etc.)>"
      summary: "<1-3 lines: key pass/fail + counts>"
      snippet: "<short pasted output excerpt>"
      artifacts:
        - "<path/to/report-or-log>"   # e.g. target/surefire-reports, jacoco report, spotbugs xml/html
```

---

## 17. Global Invariants (Summary)

- No gate may pass with missing required artifacts.
- No code-producing step may execute unless upstream gates allow it.
- Resume MUST NOT reinterpret past decisions.
- Evidence level bounds allowed claims.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE - SESSION_STATE_SCHEMA.md
