# Governance Engine Rework Plan (Session-Persistent)

Status: Architecture Baseline v1.0
Owner: repo governance workstream
Last updated: 2026-02-11

Change control (MUST):
- This baseline is updated only via pull requests.
- Changes to this baseline require stop-gate evidence for the affected area (`golden parity`, `adapter conformance`, `engine selfcheck` when applicable).

## Goal

Stabilize governance behavior so UX and safety do not regress when prompt text changes.

Key outcomes:
- deterministic runtime behavior
- versioned policy packs
- stable cross-host behavior (Desktop/CLI/CI)
- token-efficient operator UX

## 1) Architecture (Engine-first)

MUST:
- Runtime Engine is source of truth for transitions/gates.
- Prompt files (`start.md`, `master.md`, `rules.md`) are policy + UX contracts, not transition executors.
- `start.md` acts as a minimal bootloader only:
  1. load binding evidence
  2. verify engine/ruleset integrity
  3. invoke engine

Bootloader update safety (MUST):
- Installer writes engine artifacts, lockfile, and binding evidence atomically (`temp -> fsync -> replace`).
- Partial writes MUST fail closed and keep previous valid set active.
- Rollbackable active pointer is mandatory: `governance.paths.json` references exactly one active engine version and can be rolled back to the previous known-good version.
- On automatic rollback, runtime MUST emit explicit `DEVIATION` and append an audit-trail entry describing trigger and recovered version.

## 2) Module Layout

```text
governance/
  engine/
    state_machine.py
    gate_evaluator.py
    reason_codes.py
    invariants.py
  context/
    repo_context_resolver.py
    profile_detector.py
    capability_signals.py
  persistence/
    workspace_store.py
    artifact_writer.py
    session_state_repo.py
  packs/
    core/
      pack.yaml
      rules.md
    profiles/
      backend-java/
        pack.yaml
        rules.md
    addons/
      <addon-name>/
        pack.yaml
        rules.md
    templates/
      <template-name>/
        pack.yaml
        rules.md
    governance.lock
  render/
    intent_router.py
    response_renderer.py
    delta_renderer.py
  diagnostics/
    schema/
      response_envelope.schema.json
      session_state.schema.json
    quickfix_templates.json
    ux_intent_goldens.json
  adapters/
    host_adapter_base.py
    opencode_desktop_adapter.py
    cli_adapter.py
```

Separation rules:
- `workspace_store`: only `workspaces/<fingerprint>/*` artifacts/state.
- `artifact_writer`: only canonical persistence targets (no fallback redirects).

Pack execution boundary (MUST):
- Packs are policy artifacts only (metadata/rules/templates) and contain no runtime logic.

## 3) Pack Versioning and Locking

Each pack (`core/profile/addon/template`) MUST define:
- `id`
- `version` (SemVer)
- `compat` (engine min/max)
- `requires`
- `conflicts_with`

MUST:
- `governance.lock` pins resolved pack set per run/repo.
- Packs are declarative only (no executable snippets/hooks).

Pack loader enforcement (MUST):
- Allowlist file types in packs: `*.md`, `*.yaml`, `*.yml`, `*.txt`, `*.template`.
- Reject executable/script content and file types (for example `*.py`, shell hooks, embedded exec directives).

Forbidden directive patterns (MUST):
- Reject lines starting with command-injection/execution markers in pack text artifacts (for example leading `!` command lines).
- Reject YAML keys intended for runtime execution hooks (for example `exec:`, `run:`, `shell:`) in pack metadata/content files.
- Reject fenced blocks explicitly marked as shell execution payloads in policy packs.

## 4) Deterministic Runtime Flow

Flow:
1. Input normalize
2. Preflight
3. Repo-context resolution
4. Identity evidence
5. Profile detection
6. Gate evaluation
7. Rendering

Hard rules:
- `/start` once is enough (no automatic self-reinvocation loops).
- profile autodetect-first; prompt only on true ambiguity.
- canonical persistence targets are invariant.

`/start` rerun semantics (MUST):
- Manual reruns are allowed after recovery/update actions.
- Reruns MUST be idempotent (`same state -> delta-only/no-delta`).

Transient I/O retry budget (MUST):
- To handle transient host filesystem locks (for example Windows lock contention), runtime may retry single read/write operations with deterministic bounded policy.
- Default retry policy: max 3 attempts with 100ms fixed delay.
- Retries apply only within one operation attempt and MUST NOT trigger workflow-level reinvocation.
- On budget exhaustion, fail with explicit reason code and recovery guidance.

Resolver capability model (MUST):
- `host.capabilities.cwd_trust = trusted | untrusted`
- repo root priority order is deterministic:
  1. explicit root input/env
  2. valid session pointer target
  3. `cwd` only when `cwd_trust=trusted`

Profile tie-breakers (MUST):
- If multiple profile candidates exist, resolve deterministically using this order:
  1. highest priority score
  2. most matched signals
  3. newest compatible version (or lockfile pin)
  4. lexical `id` order
- Prompt operator only if a tie remains after all tie-breakers.

## 5) Hash Model (Fail-Closed)

MUST persist and compare:
- `ruleset_hash`: pack manifests + pack file bytes + compat flags + deterministic resolution order
- `activation_hash`: repo facts + capabilities + selected profile/addons + host mode + resolved canonical paths + engine version

If mismatch is unexplained: `BLOCKED`.

Mismatch recovery UX (MUST):
- Emit exactly one primary recovery action sentence and one command.
- Include a minimal deterministic diff summary for mismatch source (`engine_version|pack_hash|lockfile|capabilities|resolved_paths`).

## 6) UX Contract

Two-layer output contract:
- MUST (always):
  - status + phase/gate
  - exactly one primary next action
- SHOULD:
  - snapshot (confidence/risk/scope)
- On-demand details only (`show diagnostics`, `/audit`, `/explain-*`).

Engine identity visibility (SHOULD):
- Include runtime identity fields in `standard`/`audit` output snapshots:
  - `engine_version`
  - `engine_sha256`
  - `ruleset_hash`
  - `activation_hash`

Local mode visibility policy:
- `standard` mode SHOULD include at least `engine_version`, `ruleset_hash`, and `activation_hash` by default.
- `audit` mode MUST include all runtime identity fields listed above.

CI visibility requirement (MUST):
- In CI mode, `standard`/`audit` outputs MUST include at least:
  - `engine_version`
  - `ruleset_hash`
  - `activation_hash`

Modes:
- `compact`
- `standard`
- `audit`

Fast intents:
- `where_am_i`
- `what_blocks_me`
- `what_now`

No-change behavior:
- `state_unchanged` + delta-only/no-delta.

Token budget guard (MUST):
- Define fixed output budgets per mode (`compact`, `standard`, `audit`).
- Truncation MUST be deterministic and preserve semantic control fields.
- Truncation order:
  1. verbose details blocks
  2. long evidence expansions
  3. advisory/context prose
  4. never truncate status, phase/gate, reason code, or primary next action

## 7) Test Strategy

Required layers:
- contract tests (reason codes, envelopes, next-action coherence, write-target invariants)
- golden tests (intent outputs, `/start` dialogs)
- e2e matrix (repo-root vs backup-cwd, git/no-git, write-allowed/write-denied, profile ambiguity)
- migration tests (`SESSION_STATE` + pack schema evolution)
- mutation checks (gate logic)
- adapter conformance tests (Desktop/CLI normalized-context parity)

Evidence integrity model (SHOULD):
- Persist evidence references with deterministic identity fields:
  - `evidence_id`
  - `sha256`
  - `observed_at`
- Gate claims should reference evidence IDs/hashes to enforce "no claim without evidence" in local and CI execution.

Evidence strictness by mode:
- local mode: SHOULD enforce evidence hashing/references.
- CI mode: MUST enforce evidence hashing/references for gate claims.

Evidence freshness contract (MUST):
- Every evidence record MUST include `observed_at` (UTC ISO timestamp).
- Evidence is `stale` when older than configured TTL for its evidence class.
- Evidence classes (enum):
  - `identity_signal`
  - `preflight_probe`
  - `gate_evidence`
  - `runtime_diagnostic`
  - `operator_provided`
- Default TTL policy:
  - `identity_signal`: `ttl=0` (always re-probe on run)
  - `preflight_probe`: `ttl=0` (always re-probe on run)
  - `gate_evidence`: max 24h unless stricter gate policy applies
  - `runtime_diagnostic`: max 24h
  - `operator_provided`: session-scoped unless explicitly superseded by fresher host evidence
- Stale evidence MUST NOT be used as sole basis for passing a required gate.
- When stale evidence is detected, runtime must re-collect fresh evidence or degrade/block with explicit reason.

Adapter conformance stop-gate (MUST before engine live):
- For equivalent inputs, Desktop and CLI adapters must produce equivalent `normalized_context`
  except explicitly declared `DEVIATION.host_constraint` fields.

## 8) Rollout Waves

Welle A (stabilization, behavior-preserving):
- central resolver + write-policy + reason-code registry
- no behavior-change allowed; transition semantics must remain parity-compatible

Welle B (engine activation):
- state machine + gate evaluator live
- golden parity gate against current behavior
- engine selfcheck gate (`health`/integrity diagnostics) MUST pass before enabling live engine mode

Golden parity definition (MUST):
- `status`, `phase`, `reason_code`, and `next_action.command` must match baseline.
- UX wording/text may differ if semantic fields remain identical.

Welle C (pack system):
- versioned packs + lockfile + compat checks

Welle D (UX runtime):
- intent router + persona modes + delta renderer + token budget guard

## 9) Non-Negotiable Invariants

- no hidden fallbacks
- no silent auto-heal without explicit deviation/reporting
- CWD is untrusted in Desktop mode; resolver must prioritize explicit root/pointer evidence
- business-rules target must never drift to workspace-memory/session fields

Repository hygiene policy (recommended/pack-gated):
- Conventional branch/commit/PR-title enforcement is strongly recommended and should be applied via CI policy or dedicated governance pack (for example `release-governance`).
- This keeps engine core generic while allowing strict repo-level enforcement where required.

Conventional workflow contract (when enabled by repo policy/pack):
- Branch naming MUST be conventional and lowercase (examples: `feat/...`, `fix/...`, `refactor/...`, `docs/...`, `test/...`, `chore/...`).
- Commit subjects MUST follow Conventional Commits (`type(scope): subject` or `type: subject`).
- PR titles MUST follow Conventional Commit style and reflect the dominant change intent.
- Non-conforming branch names, commit subjects, or PR titles are release-gating failures and must be normalized before merge.

## Session Handoff Note

This file is the canonical handoff artifact for new sessions.
In a new session, load and continue from:

`docs/governance-engine-rework-plan.md`

## 10) Migration Strategy (Pragmatic)

Goal:
- Move from prompt-heavy governance behavior to engine-governed behavior without destabilizing sessions.

Phases:
- Phase 0 (prep): define old->new mapping for profile IDs, reason codes, and SESSION_STATE fields.
- Phase 1 (dual-read): engine reads legacy + new structures; writes only new structures.
- Phase 2 (engine-only): legacy reads allowed only via explicit compatibility mode with warnings.
- Phase 3 (legacy removed): unsupported legacy artifacts produce explicit recovery instructions.

MUST:
- Create automated SESSION_STATE migration with validation.
- Preserve backup of pre-migration state (`.backup`) before first write.
- Record migration metadata in SESSION_STATE (`fromVersion`, `toVersion`, `completedAt`, `rollbackAvailable`).

## 11) Pack Discovery, Integrity, and Cache

Discovery order (deterministic):
1. workspace-local overrides
2. installer-provided packs
3. user-provided packs

Discovery vs activation (MUST):
- Discovery order only builds candidate sets; it does not imply activation precedence.
- Activation MUST apply trust-policy gates before final selection.
- Workspace overrides are discovered first but activated only when explicitly allowed by trust policy.

MUST:
- Resolve dependencies/conflicts deterministically, then write resolved set to `governance.lock`.
- Verify content hash for each resolved pack.
- Fail closed when a required pack hash or compat check fails.

Cache policy (practical):
- Cache resolved pack metadata and hashes.
- Invalidate cache on: pack content hash change, engine version change, explicit clear command.

## 12) Engine Lifecycle and Rollback

MUST:
- Engine updates are staged and verified before activation.
- Activation pointer remains single-source and rollbackable.
- Keep previous known-good engine build available for immediate rollback.

Activation flow:
1. stage new engine
2. verify hash/signature (when available)
3. smoke-test with current lockfile/packs
4. atomically switch pointer
5. keep previous pointer/build for rollback

Automatic rollback triggers:
- startup crash loop
- pack compatibility failure
- hash/integrity mismatch

## 13) Observability and Recovery

MUST:
- Emit structured runtime events for key components (resolver, detector, evaluator, renderer, persistence).
- Include repo fingerprint (when known), phase/gate, reason code, result, and timing.

SHOULD:
- Provide a health diagnostic command/output for CI and local troubleshooting.
- Track core latency metrics (`startup`, `profile_detection`, `gate_eval`, `render`).

Recovery model:
- Every fatal/degraded error maps to a canonical reason code and a deterministic recovery template.
- Recovery output includes: impact, one primary action, one command, escalation hint.

## 14) Security and Trust Model

Trust levels:
- installer (highest)
- user
- workspace override (lowest)

Default trust policy:
- workspace overrides are disabled unless explicitly enabled by repo/team policy.

Trust-policy enablement sources (deterministic precedence):
1. repo policy file (for example `.governance/trust-policy.yaml`)
2. team/global config policy (for example `${CONFIG_ROOT}/trust-policy.yaml`)
3. explicit runtime flag/session override

MUST:
- Runtime must record which source enabled overrides (`policy_source`) in diagnostics/audit output.
- If sources conflict, the highest-precedence source applies.

MUST:
- Enforce pack content restrictions and loader allowlist at runtime.
- Audit security-relevant events (pack install/update, trust-level downgrade, integrity failure, rollback).
- Reject unsigned/untrusted artifacts according to configured trust policy.

## 15) Compatibility and Deprecation Policy

Stability classes:
- stable: pack schema, SESSION_STATE public contract, response envelope fields
- evolving: detection heuristics, ranking internals, rendering text
- internal: engine-private APIs and caches

Deprecation policy:
- announce deprecation
- warn for defined window
- block with migration guidance
- remove only after compatibility window

MUST:
- Mark breaking changes explicitly in changelog and migration notes.
- Provide migration tooling for any stable-surface breaking change.
