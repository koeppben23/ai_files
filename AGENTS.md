# AGENTS.md

## Purpose

This repository is governed by a normative architecture baseline.

The file `ARCHITECTURE_BASELINE.md` is the operative source of truth for architecture, drift correction, review decisions, and repair work.

All automated coding agents, including Codex-class models, must treat that file as binding.

If code, tests, comments, rails, historical docs, or prior implementation behavior conflict with `ARCHITECTURE_BASELINE.md`, the baseline wins.

Do not preserve conflicting behavior through heuristics, hidden fallback logic, compatibility layering, or silent reinterpretation.

---

## Authority and precedence

Use the following precedence order:

1. `ARCHITECTURE_BASELINE.md`
2. Canonical contracts and specs
   - `governance_spec/phase_api.yaml`
   - canonical schema/state contracts
   - canonical reason-code registries
3. Canonical runtime implementation
   - `governance_runtime/kernel/*`
   - designated canonical runtime/state/persistence modules
4. Architecture and invariant tests
5. Command rails
6. Reader-oriented docs, comments, historical files, and snapshot residue

Lower-precedence materials may refine higher-precedence materials, but may not weaken, bypass, or silently reinterpret them.

If a conflict exists, fix the lower-precedence layer.

---

## Required operating posture for coding agents

Agents must behave as architecture-repairing engineers, not as opportunistic patch generators.

### Mandatory behavior

Agents MUST:

- treat `ARCHITECTURE_BASELINE.md` as normative
- prefer architectural closure over local convenience
- remove drift instead of hiding drift
- change code to match the baseline, not the reverse
- keep patches focused and theme-bounded where possible
- add or update tests for every enforced invariant
- fail closed in code where the baseline requires fail-closed behavior
- preserve explicit product decisions already encoded in the baseline

### Prohibited behavior

Agents MUST NOT:

- invent new architecture not grounded in the baseline or canonical contracts
- preserve conflicting legacy behavior through heuristics
- add new compatibility paths to reconcile conflicting truths
- broaden fallback behavior in critical runtime paths
- silently change product behavior and describe it as refactoring
- use ambiguous interpretation when the baseline is explicit
- treat historical docs as equal authority with the baseline
- repair by adding another layer of indirection when removal of drift is possible

If the agent cannot comply without making a product-level decision not specified by the baseline, it must surface the ambiguity explicitly instead of improvising.

---

## Repository-specific non-negotiable rules

The following rules are binding and must be preserved in all repair work.

### OpenCode Desktop operating model

- Desktop default mode is `attach_existing`
- `managed` is explicit and intended for CI/headless/controlled scenarios
- `attach_existing` MUST NOT silently start a server
- if no valid target exists under `attach_existing`, the runtime MUST fail closed

### Same-session contract

The governance run is bound to one OpenCode session identity.

After binding, the same session must be used for:

- `/hydrate`
- `/ticket`
- `/review`
- `/plan`
- `/implement`

There is no automatic child-session recovery, fork recovery, or transparent rebinding.

If the bound session is gone, mismatched, or unverifiable, the correct result is a structured blocked outcome.

### Session identity resolution

The only valid resolution order is:

1. `OPENCODE_SESSION_ID`
2. `SESSION_STATE.SessionHydration.hydrated_session_id`
3. plugin signal file `active-session.json`
4. one-time initial binding through documented OpenCode APIs
5. fail closed

Session binding MUST NOT rely on:

- `directory == project_path`
- fuzzy path matching
- title similarity
- basename guessing
- “newest session wins”
- “only session available”

### Instructions vs rails

`opencode.json.instructions` contains context files.

It does not define command rails and does not replace `commands/`.

### State canonicality

Canonical state is the operative runtime truth.

Alias/legacy field resolution is allowed only in the designated normalization boundary, centered on `state_normalizer.py`.

Outside that boundary:

- runtime code MUST consume canonical fields
- runtime code MUST NOT introduce new alias probing
- writers MUST emit canonical fields only

### Reader purity

Reader modules are read-side surfaces.

They MUST NOT own mutation, hidden synchronization, fallback recovery, policy decisions, or persistence side effects.

### Persistence

Critical persistence must use canonical atomic write paths.

Agents MUST NOT introduce new critical direct writes or parallel weaker persistence paths for canonical state surfaces.

### Plugin ownership boundary

The plugin may write only signal artifacts such as `active-session.json`.

The plugin MUST NOT write canonical governance state and MUST NOT mutate `SESSION_STATE`.

---

## Required repair discipline

When asked to repair or improve this repository, the agent should work in explicit architectural themes rather than attempting a vague “fix everything” pass.

Preferred order of work:

1. Alias-/canonical-drift closure
2. Phase-6 field consistency
3. `session_reader.py` reduction to a true read-side boundary
4. mutating entrypoint slimming
5. persistence unification
6. test hardening for replay/crash/stale-state/same-session failure paths

The agent may work outside this order if a task explicitly requires it, but it must not lose track of these priorities.

---

## Mandatory patch checklist

Before finalizing a patch, the agent MUST check:

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

If any answer is yes, the patch is presumptively wrong unless explicitly justified by a higher-precedence source.

---

## Required testing discipline

Architecture work is not complete unless the relevant invariant is enforced by tests.

Depending on scope, agents must add or update:

- unit tests
- contract tests
- negative-path tests
- regression tests
- integration tests for identity/persistence/session boundaries

High-priority coverage themes include:

- replay behavior
- crash-recovery behavior
- stale-state handling
- same-session failure paths
- missing/unavailable bound session
- ambiguous initial bind
- alias regression
- critical persistence durability
- plugin/governance authority separation
- Phase-6 field consistency

---

## How agents should interpret ambiguity

If the baseline is explicit, follow it.

If the baseline is silent but canonical contracts are explicit, follow the canonical contracts.

If both are silent and the issue is architectural, do not invent architecture. Surface the ambiguity clearly.

If both are silent and the issue is implementation-local and non-architectural, make the smallest change that does not weaken the baseline.

---

## Review standard

A patch is not acceptable merely because it is small, clever, or backward-compatible.

A patch is acceptable only if it moves the implementation closer to the canonical architecture.

The following are strong signs a patch is wrong:

- it preserves drift by hiding it
- it adds fallback behavior in a critical path
- it keeps two runtime truths alive
- it treats historical docs as normative
- it solves a kernel problem inside a rail
- it solves a write-side problem inside a reader
- it weakens fail-closed behavior for convenience

---

## Expected Codex-style execution pattern

When given a repair task, the agent should generally:

1. inspect the relevant code path
2. compare behavior against `ARCHITECTURE_BASELINE.md`
3. identify exact drift points
4. make focused code changes
5. update or add tests
6. report what drift was removed and what remains

Do not claim “architecture complete” unless the enforced invariants and tests actually justify that claim.

Do not claim “no drift” unless conflicting behavior has truly been removed.

---

## Final rule

If a proposed change makes the system easier to patch but harder to reason about, it is architecturally wrong.

If a proposed change preserves legacy convenience by reintroducing ambiguity into a critical runtime boundary, it is architecturally wrong.

If a patch cannot be explained as “this moves the repository closer to `ARCHITECTURE_BASELINE.md`,” it should not be merged.
