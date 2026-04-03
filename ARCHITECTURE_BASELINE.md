# ARCHITECTURE_BASELINE.md

**Status:** Normative architecture constitution  
**Audience:** Humans, Codex-class agents, reviewers, maintainers  
**Normative strength:** **This document is the highest-level operative source of truth for architecture, drift correction, and architectural acceptance decisions in this repository.**

---

## 0. Use of normative language

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in RFC 2119.

Unless explicitly stated otherwise, all architecture rules in this document are normative.

---

## 1. Purpose

This document defines the canonical architecture, invariants, authority boundaries, compatibility limits, forbidden patterns, enforcement expectations, and closure criteria for the Governance Runtime integrated with OpenCode Desktop.

Its purpose is to eliminate architectural ambiguity and to make drift correction executable by both humans and coding agents.

When code, tests, comments, contracts, historical docs, command rails, or prior implementation behavior conflict with this document:

1. **This document wins.**
2. The lower-authority artifact MUST be changed to comply.
3. If compliance would require a product-level decision not already encoded here or in higher-precedence canonical contracts, that conflict MUST be surfaced explicitly rather than patched heuristically.

This document is intended to be precise enough that Codex-class agents can use it as a repair target instead of improvising architecture.

---

## 2. Authority and precedence

The repository MUST be interpreted using the following precedence order:

1. `ARCHITECTURE_BASELINE.md`
2. Canonical contracts and specs
   - `governance_spec/phase_api.yaml`
   - canonical schema/state contracts
   - canonical reason-code registries
3. Canonical runtime implementation
   - `governance_runtime/kernel/*`
   - designated canonical runtime/state/persistence modules
4. Architecture and invariant tests
5. Command rails under `commands/`
6. Reader-oriented docs, comments, historical files, snapshot residue, and convenience wrappers

Lower-precedence materials MAY refine higher-precedence materials, but they MUST NOT weaken, bypass, reinterpret, or silently replace them.

If a lower-precedence artifact conflicts with a higher-precedence artifact, the lower-precedence artifact is wrong and MUST be corrected.

Historical text that conflicts with this document MAY remain temporarily as residue, but it SHALL have no normative force.

---

## 3. Product model

### 3.1 Primary desktop flow

The intended desktop/user flow SHALL be:

1. Fresh install
2. `opencode-governance-bootstrap init --profile ... --repo-root ...`
3. User starts OpenCode Desktop
4. User starts or opens a session in OpenCode Desktop
5. User runs `/hydrate`
6. Governance binds to the correct OpenCode server and the correct session
7. User remains in the same bound session through `/ticket`, `/review`, `/plan`, `/implement`, and completion

### 3.2 Core runtime model

The governance runtime MUST follow this architectural rule:

**Bootstrap builds workspace knowledge.  
Deep Discovery fills canonical artifacts.  
`/hydrate` binds a concrete OpenCode session and injects compact relevant knowledge into exactly that session.  
The session is working context, not system of record.**

The OpenCode session MUST NOT be treated as governance source of truth.

Canonical persisted state and canonical persisted artifacts are the system of record.

---

## 4. Server operating modes

There SHALL be exactly two server modes:

- `attach_existing`
- `managed`

### 4.1 `attach_existing`

`attach_existing` is the default desktop/user mode.

In `attach_existing`:

- governance MUST attach to an already running local OpenCode server
- governance MUST NOT start a server
- governance MUST perform explicit discovery and validation
- if no valid server/session target exists, governance MUST fail closed
- if discovery is ambiguous, governance MUST fail closed

`attach_existing` MUST NOT silently escalate into “start one if absent”.

### 4.2 `managed`

`managed` is an explicit override intended for CI, headless, or otherwise controlled runtime scenarios.

In `managed`:

- governance MAY ensure or start a fixed-target OpenCode server
- governance MUST use the managed target semantics explicitly selected by the operator or environment
- governance MUST NOT use arbitrary discovered endpoints as a substitute for the managed target

`managed` MUST NOT be entered implicitly from desktop behavior.

---

## 5. Same-session contract

The governance workflow is defined over one bound OpenCode session identity.

After session binding succeeds:

- `/hydrate`
- `/ticket`
- `/review`
- `/plan`
- `/implement`

MUST operate on the same bound session ID.

### 5.1 Strict continuity rule

After successful binding, governance MUST NOT:

- automatically fork to a child session
- transparently rebind to a different session
- adopt a newer session opportunistically
- continue execution on a replacement session
- reinterpret loss of the bound session as permission to choose another one

If the bound session becomes unavailable, unresponsive, unverifiable, or mismatched, governance MUST produce a structured blocked result.

That blocked result SHOULD include:

- an explicit reason code or equivalent structured reason
- enough evidence to explain the failure
- concise recovery guidance

If a new session must be used, that is a new run and MUST NOT be presented as transparent recovery.

---

## 6. Session identity source of truth

### 6.1 Canonical resolution order

The canonical session identity resolution order SHALL be:

1. `OPENCODE_SESSION_ID`
2. `SESSION_STATE.SessionHydration.hydrated_session_id`
3. plugin signal file `active-session.json`
4. one-time initial bind via documented OpenCode APIs
5. fail closed

No other source MAY outrank or bypass this order.

### 6.2 Initial bind rule

If layers 1–3 do not yield a valid productive session ID, governance MAY perform one-time initial binding through documented OpenCode APIs using:

- current project resolution
- current session enumeration
- `session.projectID == current_project.id`

This initial bind MUST be explicit in behavior and evidence.

### 6.3 Forbidden binding heuristics

Session binding MUST NOT depend on:

- `session["directory"] == project_path`
- title matching
- slug guessing
- basename similarity
- fuzzy path resemblance
- newest-session-wins
- only-session-available
- arbitrary fallback to global sessions

`directory == project_path` is explicitly not a valid productive session identity contract.

---

## 7. Plugin ownership boundary

The OpenCode plugin is a signal producer, not a governance state authority.

The plugin MAY write signal artifacts such as:

- `active-session.json`

The plugin MUST NOT:

- write governance `SESSION_STATE`
- mutate canonical governance runtime state
- become a second authority for session truth
- bypass governance persistence paths

Governance alone owns canonical governance state mutation.

---

## 8. Instructions, rails, and authority

### 8.1 Command rails

Command rails are loaded from `commands/`.

Command rails are operator entrypoints and model-facing execution rails. They are not the canonical architecture authority.

### 8.2 Instructions surface

`opencode.json.instructions` MUST contain context files and contextual guidance.

`instructions` MUST NOT duplicate command rails as the source of behavioral authority.

`instructions` SHOULD provide legitimacy, framing, and context needed for correct model behavior.

### 8.3 Kernel authority

The kernel owns:

- phase truth
- transition truth
- gating truth
- admissibility truth
- fail-closed boundary behavior
- canonical runtime semantics

Rails MUST NOT redefine kernel semantics.

Rails MUST NOT invent independent fallback policy, alternate transition rules, or hidden recovery behavior.

Entrypoints MUST remain thin adapters over canonical runtime services and transitions.

---

## 9. State canonicality

Canonical state is the only allowed operative truth for runtime decisions.

Alias and legacy names MAY exist only within explicitly sanctioned compatibility boundaries.

The runtime kernel, accessors, and stateful services MUST NOT operate in a normal steady state on mixed canonical/legacy semantics.

### 9.1 Alias resolution boundary

Alias/legacy field resolution is allowed only in the canonical state normalization boundary, centered on `state_normalizer.py` and explicitly sanctioned companions.

Outside that boundary:

- code MUST consume canonical field names
- code MUST NOT introduce new alias lookup logic
- code MUST NOT read legacy names as a normal runtime path
- writers MUST emit canonical fields only

### 9.2 Forbidden alias patterns

The following are architecture violations unless explicitly approved in a higher-precedence source:

- new legacy field reads outside the normalization boundary
- mixed canonical/legacy Phase-6 logic in kernel or accessors
- new alias allowlists in operational code
- duplicate alias maps in runtime paths
- writer-side emission of canonical and legacy twins as long-term steady state
- ad hoc `x or legacy_x or LegacyX` logic in productive code

---

## 10. Kernel rule

The kernel is a canonical runtime boundary.

The kernel MUST:

- operate on canonical state
- use canonical phase and transition semantics
- fail closed on invalid or ambiguous state
- enforce gating using canonical truth
- avoid parallel legacy/canonical execution paths except in explicitly bounded short-term compatibility shims scheduled for removal

The kernel MUST NOT become a permanent host for dual semantics.

If a behavior can only be explained by “legacy path still operative,” that is presumptively drift.

---

## 11. Entrypoint rule

Entrypoints are thin rails.

Entrypoints MAY do only:

- input parsing
- input validation
- explicit precondition checks
- delegation to services, transitions, or orchestration modules
- structured result mapping

Entrypoints MUST NOT accumulate substantial:

- business logic
- transition logic
- compatibility logic
- recovery logic
- persistence policy
- multi-step state inference

If an entrypoint is responsible for parsing, policy, recovery, transition, persistence, and orchestration together, it is overweight and MUST be reduced.

---

## 12. Reader rule

Reader modules are read-only by responsibility.

A reader MAY:

- load canonical state
- normalize at the designated boundary
- present read models
- expose diagnostics
- surface blocking/evidence information

A reader MUST NOT:

- mutate session or phase state
- persist markers or reports as part of core reading
- hide write behavior behind read-side naming
- own policy decisions
- own recovery behavior
- compensate for missing kernel guarantees

If a module writes, mutates, syncs, or persists, it is not a pure reader and MUST be split accordingly.

---

## 13. Persistence rule

Critical writes MUST use the strongest standard atomic persistence path available in the repository.

No new critical file writes MAY bypass canonical atomic write helpers.

The write path for canonical surfaces MUST be:

- centralized
- explicit
- crash-conscious
- consistent
- auditable

### 13.1 Forbidden persistence patterns

The following are architecture violations:

- new critical `write_text()` or `write_bytes()` direct writes bypassing atomic helpers
- multiple competing atomic implementations for the same canonical surface class
- best-effort writes treated as success
- partial writes treated as success
- JSONL appends in critical paths without a canonical locking/sink policy
- state mutation without auditable persistence behavior

### 13.2 Single strongest path rule

For each critical persistence surface, there SHOULD be one strongest canonical write path.

Competing unequal write paths for the same surface are presumptively drift and SHOULD be consolidated.

---

## 14. Hydration contract

`/hydrate` is the first session-bound governance step.

A successful hydration MUST:

1. resolve the productive OpenCode server according to the active server mode
2. validate server reachability
3. resolve the canonical productive session identity
4. validate required canonical knowledge/artifact inputs
5. construct a compact hydration brief from canonical persisted knowledge
6. inject that brief into the exact bound session
7. persist governance-side hydration evidence
8. persist or update canonical session binding metadata

Hydration MUST NOT silently change session identity as a side effect of refresh.

Hydration MAY refresh evidence for the same bound session.

If any mandatory precondition or persistence step fails, hydration MUST fail closed.

### 14.1 Minimum canonical hydration fields

A successful hydration MUST persist at least the following governance-side binding metadata:

- `status: "hydrated"`
- `hydrated_session_id`
- `resolved_server_url`
- `binding_source`
- `hydrated_at`

`binding_source` MUST be one of:

- `env`
- `session_state`
- `plugin`
- `initial_bind`

---

## 15. Phase and gate truth

Routing, execution, and validation truth belong to canonical phase/spec contracts and kernel execution.

The runtime MUST be phase-driven, not prose-driven and not rail-defined.

### 15.1 Gate rule

A gate is open only if kernel-enforced state proves it open.

No command rail, comment, or historical assumption may treat a gate as “close enough”.

### 15.2 Ticket intake readiness

There SHALL be exactly one authoritative readiness gate for intake:

- `ticket_intake_ready`

Observability or convenience fields such as `phase_ready` MUST NOT be used as authoritative admission truth.

If code admits productive intake based on a non-authoritative field, that code is in drift.

---

## 16. Phase-6 field consistency

Phase-6 review/iteration field names MUST be consistent across:

- alias mapping
- canonical state types
- accessors
- kernel
- writers
- readers
- tests

There MUST be exactly one canonical name for each Phase-6 field.

Legacy names MAY exist only in normalization or explicitly bounded compatibility layers and MUST NOT remain as parallel operative truth.

---

## 17. Ticket semantics contract

`/ticket` is the intake rail.

It is a mutating intake command.

Its job is to persist intake evidence and reroute canonical state through the kernel.

`/ticket` is not planning, approval, or implementation.

If the product semantics accept both ticket-like and task-like intake, naming and copy SHOULD NOT imply a stricter semantics than the implementation actually enforces.

---

## 18. Deep discovery and canonical artifacts

Deep repository discovery is a canonical runtime responsibility.

The following discovery components SHALL be treated as productive discovery components:

- `deep_repo_discovery.py`
- `semantic_discovery.py`
- canonical artifact persistence orchestration

The runtime MUST maintain canonical discovery artifacts including:

- `repo-cache.yaml`
- `repo-map-digest.md`
- `workspace-memory.yaml`
- `decision-pack.md`

These artifacts are canonical compact knowledge inputs for hydration and downstream governance work.

They are not mere advisory scratchpads.

Hydration SHOULD consume compact relevant knowledge from these artifacts and project that knowledge into the bound session.

---

## 19. Allowed compatibility boundaries

Compatibility behavior is allowed only in explicitly bounded places.

### Allowed

- state normalization boundary
- short-lived repository compatibility bridges with explicit deprecation intent
- installer migration paths with explicit one-way upgrade behavior

### Not allowed

- durable kernel-level parallel semantics
- entrypoint-local ad hoc fallback logic
- writer-side long-term emission of both legacy and canonical forms
- product-critical project/session identity heuristics
- reader-owned repair or synchronization behavior
- second-authority session truth

Any compatibility layer that survives by becoming a second runtime truth is architecturally wrong.

---

## 20. Forbidden patterns

The following are prohibited unless explicitly authorized by a higher-precedence source.

### 20.1 Session and binding

- matching sessions via `directory == project_path`
- silent fallback from strict binding to heuristic discovery
- automatic fork or child-session recovery after binding
- rebinding session identity without explicit new-run semantics
- silent adoption of arbitrary discovered sessions

### 20.2 State and aliasing

- new legacy reads outside normalization
- duplicate alias maps in productive modules
- long-term dual legacy/canonical writer behavior
- productive runtime logic that probes multiple field names for one semantic field

### 20.3 Persistence

- bypassing canonical atomic write helpers for critical writes
- parallel weaker write paths for canonical surfaces
- non-auditable critical state mutation
- treating partial persistence as success

### 20.4 Entrypoints

- significant policy logic in entrypoints
- transition logic embedded directly in entrypoints
- entrypoints combining parsing, policy, state inference, persistence, review orchestration, and recovery logic

### 20.5 Readers

- persistence inside read-only modules
- hidden synchronization in readers
- “reader” modules with effective write-side responsibilities
- dead code after `return`

### 20.6 Errors and reason codes

- uncatalogued reason codes in productive paths when canonical registries exist
- broad `except Exception` in critical runtime boundaries without strong justification
- string-matching production error classification where structured classification exists

### 20.7 Rails and instructions

- duplicating command rails in `instructions`
- command rails that describe obsolete server or port behavior as current truth
- rails that omit necessary legitimacy context where model confusion is known to occur

---

## 21. Known drift to eliminate

The following debt themes are explicit repair targets, not optional polish.

### 21.1 Alias drift

Goal:

- eliminate non-central alias resolution from operative runtime paths

### 21.2 Phase-6 field drift

Goal:

- unify Phase-6 field names across alias map, canonical models, accessors, kernel, writers, readers, and tests

### 21.3 `session_reader.py` overload

Goal:

- split read-only concerns from state mutation, gate sync, persistence, and report generation

### 21.4 Persistence drift

Goal:

- consolidate critical persistence onto one strongest standard path per surface

### 21.5 Kernel legacy/canonical parallelism

Goal:

- remove durable dual semantics from kernel runtime logic

### 21.6 Heavy mutating entrypoints

Goal:

- move business logic, state inference, and recovery logic below the rail layer into services or transition modules

### 21.7 Contract compiler fragility

Goal:

- treat compiler output as heuristic or seed unless and until stronger guarantees are explicitly established

### 21.8 Test hardening gaps

Goal:

- add replay, crash-recovery, stale-state, and same-session failure-path coverage

---

## 22. OpenCode integration rules

### 22.1 Commands

Command files under `commands/` are slash-command rails.

They SHOULD use OpenCode-documented command metadata where appropriate.

### 22.2 Instructions

`instructions` in `opencode.json` provide contextual model guidance.

They MUST contain context/reference documents needed for governance legitimacy and framing.

They MUST NOT be used to duplicate rails already loaded from `commands/`.

### 22.3 Desktop attach flow

Default desktop flow is `attach_existing`.

That means governance MUST:

- discover a running local OpenCode server
- bind to the correct current project/session using canonical rules
- hydrate that exact bound session
- fail closed if any required step fails

### 22.4 Managed flow

Managed flow is an explicit override.

That means governance MAY:

- ensure or start a managed server
- bind to that explicit server target

Once binding succeeds, the same-session rule still applies.

---

## 23. Testing requirements

A patch is not architecture-complete if it changes behavior but leaves the governing invariant untested.

### 23.1 Required test classes

Depending on scope, architecture changes MUST add or update appropriate:

- unit tests
- contract tests
- negative-path tests
- regression tests
- integration tests where identity, gating, persistence, or session continuity matter

### 23.2 Required hardening themes

The suite SHOULD increasingly cover:

- replay behavior
- crash-recovery behavior
- stale-state handling
- same-session failure behavior
- session unavailable after binding
- ambiguous initial bind
- no-match initial bind
- alias regression
- critical persistence durability
- plugin/governance authority separation
- Phase-6 field consistency

### 23.3 Reason-code rule

Any new reason code introduced into productive behavior MUST be added to canonical reason-code locations and MUST be tested in at least one production-relevant path.

---

## 24. Codex working rules

Codex-class agents and automated repair systems MUST treat this file as normative.

### 24.1 Repair behavior

When code conflicts with this document:

- agents MUST change the code
- agents MUST NOT silently preserve conflicting behavior
- agents MUST NOT add heuristics to reconcile incompatible truths
- agents SHOULD prefer removal of drift over preservation of convenience compatibility

### 24.2 Escalation behavior

If this document is insufficiently specific for a required architectural decision:

- agents MUST surface the ambiguity explicitly
- agents MUST NOT invent architecture
- agents MUST NOT silently broaden compatibility behavior

### 24.3 Patch discipline

Patches SHOULD be:

- small
- theme-bounded where possible
- test-backed
- explicit about which invariant they enforce

### 24.4 Mandatory patch checklist

Before finalizing a patch, an agent MUST check:

1. Does this remove drift, or merely add another compatibility layer?
2. Does this introduce any new alias resolution outside the normalization boundary?
3. Does this preserve the strict same-session contract?
4. Does this rely on session heuristics where canonical identity exists?
5. Does this bypass the strongest canonical persistence path?
6. Does this make an entrypoint heavier instead of thinner?
7. Does this let a reader own mutation or policy?
8. Does this create or preserve dual legacy/canonical runtime semantics?
9. Does this silently broaden fallback behavior at a critical boundary?
10. Are the relevant invariants tested?

If any answer is “yes”, the patch is presumptively wrong unless explicitly justified by a higher-precedence source.

---

## 25. Merge blockers and automatic reject conditions

A patch SHOULD be rejected if it does any of the following without an explicit higher-precedence justification:

- preserves drift by adding another compatibility layer
- weakens fail-closed behavior in a critical boundary
- keeps two operative runtime truths alive
- treats historical docs as equal authority with this file
- solves a kernel problem inside a rail
- solves a write-side problem inside a reader
- reintroduces heuristic session identity
- introduces new critical persistence paths outside canonical atomic helpers
- silently changes product behavior while presenting it as refactor-only work
- claims architecture closure without corresponding tests and invariant enforcement

---

## 26. Architecture closure criteria

The architecture SHALL be considered materially closed enough for feature-first development only when all of the following are true:

1. Alias resolution is centralized in practice, not only in aspiration.
2. Kernel runtime semantics operate on canonical truth without durable parallel legacy truth.
3. Phase-6 field naming is fully aligned across state, accessors, kernel, writers, readers, and tests.
4. Session binding is explicit, stable, project-correct, and same-session strict.
5. No productive session identity heuristics remain.
6. Reader modules are read-only in responsibility.
7. Mutating entrypoints are thin rails over services or transitions.
8. Critical persistence uses the strongest canonical atomic path per surface.
9. Plugin and governance authority are cleanly separated.
10. Rails and instructions reflect current OpenCode integration behavior.
11. High-risk failure paths are covered by tests.
12. Contradictory lower-authority docs are updated, removed, or clearly superseded.

If any of these conditions are false, the system is not yet in the “feature development only” state.

---

## 27. Non-goals

This document does not require:

- instant removal of every compatibility shim in one patch
- zero heuristics in all auxiliary tooling
- immediate deletion of every historical artifact

This document does require:

- no new drift
- explicit movement toward closure
- removal of conflicting truths from critical runtime boundaries
- architectural honesty about what remains unresolved

---

## 28. Supersession notes

Any historical text that says or implies any of the following is superseded by this document:

- fixed-port desktop assumptions as productive truth
- session matching by `directory == project_path`
- instructions-as-rails authority
- automatic child or fork session recovery
- implicit server start in `attach_existing`
- durable non-canonical field compatibility as normal runtime mode
- reader-owned runtime behavior
- plugin-owned governance state mutation

Such text MAY remain temporarily as residue, but SHALL have no normative force.

---

## 29. Final rule

If a change makes the system easier to patch but harder to reason about, it is architecturally wrong.

If a change preserves legacy convenience by reintroducing ambiguity into a critical runtime boundary, it is architecturally wrong.

If a patch cannot be explained as “this moves the implementation closer to the canonical contract defined here,” it SHOULD NOT be merged.
