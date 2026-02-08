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

1) The current step is an **explicit gate** (Phase 5 / 5.3 / 5.4 / 5.5 / 5.6 / 6).
2) `SESSION_STATE.Mode = BLOCKED`.
3) A reviewer/audit request requires it (e.g., “show full session state”).
4) Phase 2 just completed (repo discovery) and this is the first time `RepoMapDigest` is produced.
5) `SESSION_STATE.ConfidenceLevel < 70` (DRAFT/BLOCKED; expanded state required to resolve ambiguity safely).

### 1.3 Size constraint (recommended)

- MIN SHOULD be kept below ~40 lines.
- FULL SHOULD remain compact and prefer digests over full enumerations.

---

## 1.4 Bootstrap State (Phase 1.1)

The bootstrap phase establishes whether the governance system is **explicitly activated** for the current session.
This prevents implicit or accidental execution of the workflow.

### Required Bootstrap Fields

During Phase `1.1-Bootstrap`, the session MUST include:

- `SESSION_STATE.Bootstrap.Present` (boolean)
- `SESSION_STATE.Bootstrap.Satisfied` (boolean)
- `SESSION_STATE.Bootstrap.Evidence` (string)

### Semantics

- `Present = true` means an explicit bootstrap declaration was provided by the operator.
- `Satisfied = true` means the declaration is semantically sufficient to activate the governance system.
- `Evidence` MUST briefly describe how the bootstrap was established (e.g., "explicit bootstrap declaration in session header").

### Invariants

- `SESSION_STATE.Next` MUST be set at the end of every phase output.
- `continue.md` MUST execute ONLY the step referenced by `SESSION_STATE.Next`.
- Every response containing `SESSION_STATE` MUST end with a terminal summary line:
  - `NEXT_STEP: <value of SESSION_STATE.Next>`
  - This line MUST appear after the `SESSION_STATE` block and be the last assistant-authored line.

### Path invariants (binding)

Canonical path fields in `SESSION_STATE` are any fields whose semantic purpose is to point to a file location to be read/written by the workflow, including (non-exhaustive):
- `LoadedRulebooks.*`
- `BusinessRules.InventoryFilePath`
- `RepoCacheFile.SourcePath` / `RepoCacheFile.TargetPath`
- `RepoMapDigestFile.*Path`
- `WorkspaceMemoryFile.*Path`
- any field ending in `Path`, `FilePath`, or named `TargetPath` / `SourcePath`
(Excludes evidence-only fields such as `RulebookLoadEvidence.*`.)

BINDING:
- Forbidden patterns in canonical path fields (aligned with master.md persistence rules):

  1) OS-specific patterns (→ BLOCKED-PERSISTENCE-PATH-VIOLATION):
     - Windows drive prefixes: `^[A-Za-z]:\\` or `^[A-Za-z]:/`
     - Backslashes: `\`
     - Parent traversal: `..`

  2) Degenerate patterns (→ BLOCKED-PERSISTENCE-TARGET-DEGENERATE):
     - Single drive letter: `^[A-Za-z]$` (example: `C`)
     - Drive root token: `^[A-Za-z]:$` (example: `C:`)
     - Drive-relative path: `^[A-Za-z]:[^\\/].*`
     - Single-segment relative path WITHOUT `${...}`:
       - Pattern: `^[^\\/]+$` AND NOT starting with `${`
       - Examples: `rules.md`, `tmp`, `config`

- Exception (evidence-only): absolute paths (including backslashes) MAY appear inside evidence fields
  (e.g., `RulebookLoadEvidence.*`) if pasted from host output, but canonical variable-based expressions MUST still be used for canonical path fields.

FAIL-CLOSED:
- If any canonical path field violates the forbidden patterns:
  - `SESSION_STATE.Mode` MUST be `BLOCKED`
  - `SESSION_STATE.Next` MUST be one of:
    - `BLOCKED-PERSISTENCE-PATH-VIOLATION`
    - `BLOCKED-PERSISTENCE-TARGET-DEGENERATE`
  - Output MUST name the violating field(s) and provide the corrected variable-based form.

Session-state storage topology (binding):
- Canonical session payload location is repo-scoped: `${SESSION_STATE_FILE}` = `${REPO_HOME}/SESSION_STATE.json`.
- Global `${SESSION_STATE_POINTER_FILE}` is a pointer/locator for the active repo session and MUST NOT hold multi-repo session payload as canonical state.
- When both are present, runtime operations MUST resolve through `${SESSION_STATE_POINTER_FILE}` to `${SESSION_STATE_FILE}` for the active repo.

Mapping of violations to BLOCKED-Reasons:
- Backslash (`\`) → BLOCKED-PERSISTENCE-PATH-VIOLATION
- Drive prefix (`C:\`, `C:/`) → BLOCKED-PERSISTENCE-PATH-VIOLATION
- Parent traversal (`..`) → BLOCKED-PERSISTENCE-PATH-VIOLATION
- Single drive letter (`C`) → BLOCKED-PERSISTENCE-TARGET-DEGENERATE
- Drive root token (`C:`) → BLOCKED-PERSISTENCE-TARGET-DEGENERATE
- Single segment without `${...}` → BLOCKED-PERSISTENCE-TARGET-DEGENERATE

---

## 2. Required Keys (Phase 1+)

NOTE:
Phase 1.1 (Bootstrap) is the only phase allowed to emit a partial SESSION_STATE without all required keys listed below.

Once Phase 1.1 (bootstrap) completes successfully, these keys MUST exist:

- `SESSION_STATE.Phase` (enum; see Section 3)
- `SESSION_STATE.Mode` (enum; see Section 4)
- `SESSION_STATE.ConfidenceLevel` (integer 0–100)
- `SESSION_STATE.Next` (string; canonical continuation pointer)
- `SESSION_STATE.Bootstrap.Present` (boolean)
- `SESSION_STATE.Bootstrap.Satisfied` (boolean)
- `SESSION_STATE.Bootstrap.Evidence` (string)
- `SESSION_STATE.Scope` (object; see Section 6.5)
- `SESSION_STATE.LoadedRulebooks.core` (string path OR `""` if deferred until Phase 4)
- `SESSION_STATE.LoadedRulebooks.profile` (string path OR `""` if deferred/planning-only)
- `SESSION_STATE.LoadedRulebooks.templates` (string path OR `""` if deferred until Phase 4 or not applicable)
- `SESSION_STATE.LoadedRulebooks.addons` (object map addon_key -> string path; default `{}`)
- `SESSION_STATE.AddonsEvidence` (object map addon_key -> evidence object; default `{}`)
- `SESSION_STATE.RulebookLoadEvidence` (object; see Section 6.4)
- `SESSION_STATE.ActiveProfile` (string OR `""` if deferred until post-Phase-2)
- `SESSION_STATE.ProfileSource` (enum; see Section 5)
- `SESSION_STATE.ProfileEvidence` (string)
- `SESSION_STATE.Gates` (object; see Section 8)

---

## 2.1 Optional Diagnostics Keys (Self-Audit)

The session state MAY include a diagnostics pointer block for the most recent `/audit` run.
This block is **descriptive only** and MUST NOT be interpreted as normative authority.

### 2.1.1 `SESSION_STATE.Audit.LastRun` (optional)

If present, it MUST follow this shape:

- `SESSION_STATE.Audit.LastRun.Timestamp` (string; ISO8601 date-time)
- `SESSION_STATE.Audit.LastRun.Mode` (enum: `chat-only|repo-aware`)
- `SESSION_STATE.Audit.LastRun.ReportRef` (string)
- `SESSION_STATE.Audit.LastRun.ReportHash` (string; `sha256:<hex>` OR `none`)
- `SESSION_STATE.Audit.LastRun.Status` (enum: `ok|blocked`)
- `SESSION_STATE.Audit.LastRun.ReasonKeys` (list of strings; may be empty)

### 2.1.2 Mutation constraints (binding)

`/audit` MUST be read-only with respect to workflow control fields.
It MUST NOT modify any of:
- `SESSION_STATE.Phase`
- `SESSION_STATE.Mode`
- `SESSION_STATE.ConfidenceLevel`
- `SESSION_STATE.Next`
- `SESSION_STATE.Gates`
- any discovery, plan, or evidence fields

If `/audit` writes to `SESSION_STATE`, it MAY update **only** `SESSION_STATE.Audit.LastRun.*`.
`/audit` MUST NOT influence or change gate statuses; it may only report them.

### 2.1.3 Path invariants for `ReportRef` (binding)

If `ReportRef` is a file path (repo-aware mode), it MUST follow canonical path invariants:
- MUST be variable-based (e.g., `${WORKSPACES_HOME}/...`)
- MUST NOT be an absolute OS path
- MUST NOT contain backslashes, drive prefixes, or `..`

If chat-only mode (no persistence), `ReportRef` MUST be `not-persisted`.

### Lazy-loading invariants (binding)

- Until Phase 2 completes:
  - `ActiveProfile` MAY be `""`
  - `ProfileSource` MUST be `"deferred"`
  - `LoadedRulebooks.profile` MAY be `""`

- Until Phase 4 begins:
  - `LoadedRulebooks.core` MAY be `""`
  - `LoadedRulebooks.templates` MAY be `""`

- If Phase 4 begins and `LoadedRulebooks.core` is still `""`:
  → WORKFLOW MUST BE BLOCKED

- If Phase 4 begins and the `ActiveProfile` mandates templates, and `LoadedRulebooks.templates` is still `""`:
  → WORKFLOW MUST BE BLOCKED

- If Phase 4 begins and the workflow determines an addon is required (evidence-based), but the addon rulebook is not available:
  - The workflow MUST NOT silently ignore it.
  - `SESSION_STATE.AddonsEvidence.<addon_key>.status` MUST be `missing-rulebook`.
  - The plan MUST include an explicit operator action to add/write the addon rulebook.
  - The assistant MUST clearly scope its output to what can be guaranteed without the missing addon rulebook.
  - If addon manifest declares `addon_class = required`: WORKFLOW MUST BE BLOCKED (`BLOCKED-MISSING-ADDON:<addon_key>`).
  - If addon manifest declares `addon_class = advisory`: continue non-blocking with WARN + recovery action.

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
- `2.1-DecisionPack` (decision pack distillation)
- `1.5-BusinessRules` (business rules discovery)
- `3A` (API inventory)
- `3B-1` (API logical validation)
- `3B-2` (contract validation spec ↔ code)
- `4` (ticket execution / plan)
- `5` (architecture gate)
- `5.3` (test quality gate)
- `5.4` (business rules compliance gate)
- `5.5` (technical debt gate)
- `5.6` (rollback safety gate)
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
- If `ConfidenceLevel < 70`, `Mode` MUST be `DRAFT` or `BLOCKED` (MUST NOT be `NORMAL` or `DEGRADED`).
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

## 6. Workflow Supporting State

### 6.1 Component Scope (Monorepos / Bounded Ownership)

Optional but strongly recommended for monorepos:

- `SESSION_STATE.ComponentScopePaths` (array of repo-relative paths)
- `SESSION_STATE.ComponentScopeSource` (enum: `user-explicit` | `assistant-proposed`)
- `SESSION_STATE.ComponentScopeEvidence` (string)

**Invariant**
- If `ComponentScopePaths` is set, profile detection, discovery summaries, and recommendations MUST prefer signals inside those paths.

### 6.2 Next (Phase Pointer)

`SESSION_STATE.Next` is a string describing the next executable step, e.g.:
- `Phase2-RepoDiscovery`
- `Phase2.1-DecisionPack`
- `Phase4-TicketExecution`
- `Phase5-ArchitectureGate`
- `BLOCKED-<reason>`

**Invariant**
- `Next` MUST NOT skip mandatory gates.
- Render contract: after emitting `SESSION_STATE`, output `NEXT_STEP: <SESSION_STATE.Next>` as the terminal line.

### 6.3 Canonical BLOCKED Next Pointers (recommended)

The following BLOCKED pointers are canonical and SHOULD be used when applicable:

- `BLOCKED-BOOTSTRAP-NOT-SATISFIED`
- `BLOCKED-MISSING-CORE-RULES`
- `BLOCKED-MISSING-PROFILE`
- `BLOCKED-AMBIGUOUS-PROFILE`
- `BLOCKED-MISSING-TEMPLATES`
- `BLOCKED-MISSING-ADDON:<addon_key>` (required when `addon_class = required` and the triggered rulebook is missing)
- `BLOCKED-ADDON-CONFLICT` (required when same-precedence addon/template constraints are mutually incompatible or non-deterministic)
- `BLOCKED-RULEBOOK-EVIDENCE-MISSING`
- `BLOCKED-WORKSPACE-MEMORY-INVALID`
- `BLOCKED-MISSING-EVIDENCE`
- `BLOCKED-VARIABLE-RESOLUTION`
- `BLOCKED-RESUME-STATE-VIOLATION`

### 6.4 Rulebook Load Evidence (canonical)

To prevent implicit/fictional rulebook loading, the session MUST track load evidence.

#### Field

- `SESSION_STATE.RulebookLoadEvidence` (object)

Recommended shape (minimal):

```yaml
SESSION_STATE:
  RulebookLoadEvidence:
    core: "<path | hash | tool-output | user-provided | deferred>"
    profile: "<path | hash | tool-output | user-provided | deferred>"
    templates: "<path | hash | tool-output | user-provided | not-applicable>"
    addons:
      kafka: "<path | hash | tool-output | user-provided>"
```

#### Binding invariants

- If any of the following fields is non-empty:
  - `LoadedRulebooks.core`
  - `LoadedRulebooks.profile`
  - `LoadedRulebooks.templates`
  - `LoadedRulebooks.addons.*`
  then `RulebookLoadEvidence` MUST be present and MUST include corresponding keys (including addon keys).
- If rulebook load evidence cannot be produced due to host/tool limitations:
  - `Mode = BLOCKED`
  - `Next = BLOCKED-RULEBOOK-EVIDENCE-MISSING`
  - No phase completion may be claimed.

### 6.4.1 Addons Evidence (canonical)

To prevent implicit/fictional addon activation and to make addon loading auditable, the session MUST track
evidence for each evaluated addon key.

#### Field

- `SESSION_STATE.AddonsEvidence` (object map addon_key -> object)

Recommended minimal shape:

```yaml
SESSION_STATE:
  AddonsEvidence:
    kafka:
      signals: ["pom.xml: org.springframework.kafka:spring-kafka", "code: @KafkaListener"]
      required: true
      status: loaded | skipped | missing-rulebook
```

#### Binding invariants

- `AddonsEvidence` MUST exist after bootstrap completes (default `{}`).
- If an addon key is present in `LoadedRulebooks.addons`, the corresponding `AddonsEvidence.<addon_key>` MUST exist.
- If an addon key is evaluated during discovery/planning (required or not), `AddonsEvidence.<addon_key>` SHOULD exist
  with `required` and at least one signal when evidence is available.
- If an addon is required by signals but the rulebook is unavailable, `AddonsEvidence.<addon_key>.status` MUST be
  `missing-rulebook` and the plan MUST include the operator action (write/add the addon rulebook).
- If that addon is `addon_class = required`, `Mode` MUST be `BLOCKED` with `Next = BLOCKED-MISSING-ADDON:<addon_key>`.

### 6.5 Scope (canonical)

`SESSION_STATE.Scope` captures the current problem space.

Recommended structure:

```yaml
SESSION_STATE:
  Scope:
    Repository: "<repo name or identifier>"
    RepositoryType: "<e.g., Spring Boot (Maven, Java 21) | Nx monorepo>"
    ExternalAPIs: []
    BusinessRules: not-applicable | pending | extracted
```

Binding:
- After Phase 2, `Scope.Repository` and `Scope.RepositoryType` SHOULD be set unless repo access is impossible.
- If Phase 1.5 is executed, `Scope.BusinessRules` MUST NOT be `not-applicable`.

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
      Required: ["ArchitectureDecisions", "DecisionDrivers", "DecisionPack", "TouchedSurface"]
      Provided:
        ArchitectureDecisions: present | missing | not-applicable
        DecisionDrivers: present | missing | not-applicable
        DecisionPack: present | missing | not-applicable
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

### 8.1b Gate Scorecards (Objective Review Contract)

Each explicit gate SHOULD emit a machine-checkable scorecard.

Recommended structure:

```yaml
SESSION_STATE:
  GateScorecards:
    P5-Architecture:
      Score: 8
      MaxScore: 10
      Criteria:
        - id: ARCH-BOUNDARIES
          weight: 3
          critical: true
          result: pass | fail | partial | not-applicable
          evidenceRef: EV-001
      Decision: approved | rejected
```

Binding rules:
- In FULL mode at explicit gates, `GateScorecards.<gate>` MUST be present.
- If a criterion has `critical: true` and `result = fail`, that gate MUST NOT pass.
- `Decision` MUST be consistent with criteria results and gate status.

### 8.2 Phase 5.6 – Rollback Safety Gate

Validates that the planned change is rollback-safe and that reversibility is explicitly addressed when needed.

Applicable when any of the following is planned/observed:
- schema or data migrations (`TouchedSurface.SchemaPlanned` non-empty)
- externally-consumed contract changes (`TouchedSurface.ContractsPlanned` non-empty)
- irreversible state transitions

Requirements (FULL mode at explicit gate):
- `SESSION_STATE.RollbackStrategy` MUST be present and actionable when applicable.
- If `RollbackStrategy.DataMigrationReversible = false`, explicit safety steps MUST be documented (backups, dual-write, shadow reads, etc.).

Gate result mapping:
- `approved`: rollback strategy is credible
- `rejected`: rollback strategy missing/unsafe
- `not-applicable`: no schema/contract/irreversible impact

### 8.2a Risk Tiering Contract (for shared tiering rulebooks)

If canonical risk-tiering is used by active profile/addons, the session SHOULD include:

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

Binding when the field is present:
- `ActiveTier` must be one of `TIER-LOW|TIER-MEDIUM|TIER-HIGH`.
- If `MissingEvidence` is non-empty, any gate depending on this tiering MUST NOT be marked as pass.

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

If the ticket changes an externally-consumed contract (OpenAPI, events, shared schema), the session MUST include:

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

## 12. Decision Pack (Phase 2.1; recommended)

To reduce cognitive load, Phase 2 SHOULD produce a compact **Decision Pack**.
If produced:

- `SESSION_STATE.DecisionPack` (array)
  - each entry SHOULD include: `id`, `decision`, `options`, `recommendation`, `evidence`, `what_changes_it`
  - optional lifecycle fields: `status`, `supersedes`, `supersededBy`

---

## 13. Ticket Record (Phase 4+; required by rules)

When Phase 4 planning is produced, the workflow MUST include:
- `SESSION_STATE.TicketRecordDigest` (one-line summary)
- `SESSION_STATE.NFRChecklist` (object; may be elided in MIN if digest captures exceptions)
- `SESSION_STATE.MandatoryReviewMatrix` (object; required by `rules.md`/`master.md` for PR readiness)

Recommended `MandatoryReviewMatrix` shape:

```yaml
SESSION_STATE:
  MandatoryReviewMatrix:
    TicketClass: api-change | schema-migration | business-rule-change | security-change | performance-change | ui-change | mixed
    RiskTier: LOW | MEDIUM | HIGH
    RequiredArtifacts:
      - name: "<artifact-name>"
        required: true
        evidenceRef: "<BuildEvidence item id/scope or not-verified>"
```

This is further specified as binding in `rules.md` (Ticket Record section).

---

## 14. Business Rules State (Phase 1.5+)

If Phase 1.5 is executed, the session MUST include `SESSION_STATE.BusinessRules`:

```yaml
SESSION_STATE:
  BusinessRules:
    InventoryFilePath: "<path expression>"
    InventoryLoaded: true | false
    InventoryFileStatus: written | write-requested | not-applicable
    InventoryFileMode: create | update | unknown
    ExtractedCount: <integer>
    Coverage:
      Code: "<n>/<total>"
      Tests: "<n>/<total>"
      DB: "<n>/<total>"
    Notes: "<short text>"
```

Binding:
- If `Gates.P5.4-BusinessRules` is evaluated, `BusinessRules` MUST be present.

---

## 15. Build Evidence

```yaml
BuildEvidence:
  status: not-provided | partially-provided | provided-by-user
  notes: "<what exists or is missing>"
  items:                # optional but strongly recommended; enables reviewer-proof verification
    - id: "EV-001"
      tool: "<maven|gradle|npm|spotbugs|checkstyle|archunit|openapi|pact|...>"
      command: "<exact command executed>"
      result: pass | fail | unknown
      scope: "<what this evidence covers (unit tests, integration tests, contract validation, etc.)>"
      summary: "<1-3 lines: key pass/fail + counts>"
      snippet: "<short pasted output excerpt>"
      artifacts:
        - "<path/to/report-or-log>"   # e.g. target/surefire-reports, jacoco report, spotbugs xml/html
```

---

## 16. Workspace Memory File (OpenCode-only, recommended)

Workspace Memory stores stable, repo-specific defaults (conventions + patterns) across sessions to reduce drift.

If used, the assistant SHOULD populate:

- `SESSION_STATE.WorkspaceMemoryFile` (object)

Recommended structure:

```yaml
SESSION_STATE:
  WorkspaceMemoryFile:
    SourcePath: "<path expression>"        # e.g., ${REPO_HOME}/workspace-memory.yaml
    TargetPath: "<path expression>"        # same as SourcePath when writing
    Loaded: true | false
    Valid: true | false
    InvalidationReason: "<short text>"     # empty when Valid=true
    FileStatus: written | write-requested | not-applicable
    Summary: "<short digest>"              # optional; 3-8 bullets serialized
```

Validation rules (Binding when the file exists):
- YAML must parse.
- Root key `WorkspaceMemory` must exist.
- `WorkspaceMemory.Version` must equal `"1.0"`.
- If invalid, the workflow MUST enter `Mode=BLOCKED` with reason `BLOCKED-WORKSPACE-MEMORY-INVALID`.

---

## 17. Resume Integrity (Canonical)

Resume MUST NOT reinterpret or mutate past decisions.

Recommended structure:

```yaml
SESSION_STATE:
  Resume:
    Source: initial | continue | resume
    LockedFields:
      - ActiveProfile
      - ArchitectureDecisions
      - DecisionPack
      - Gates
```

Binding:
- If `Resume.Source = resume`, then fields in `LockedFields` MUST NOT change.
- If a locked field change is detected, the workflow MUST enter:
  - `Mode = BLOCKED`
  - `Next = BLOCKED-RESUME-STATE-VIOLATION`

---

## 18. Global Invariants (Summary)

- No gate may pass with missing required artifacts.
- No code-producing step may execute unless upstream gates allow it.
- Resume MUST NOT reinterpret past decisions.
- Evidence level bounds allowed claims.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE - SESSION_STATE_SCHEMA.md
