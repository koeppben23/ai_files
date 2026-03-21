# Governance Implement

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/implement` starts execution of the approved implementation plan after approved Phase 6 governance review.
The command is mutating. It orchestrates the resolved implementation executor (default: active OpenCode Desktop LLM binding; optional explicit override) and writes governance diagnostics/state.

`/implement` follows a controller/executor split (default executor: active OpenCode Desktop LLM binding):
- load approved plan, hotspots, constraints, and required checks
- write executor input context (`.runtime_state/implementation/llm_edit_context.json`)
- resolve executor in priority order: explicit override first, otherwise active OpenCode Desktop LLM binding
- invoke the resolved implementation executor (the only actor allowed to change domain files)
- run internal implementation self-review (validation-only; no local domain edits)
- collect git diff evidence and validate plan-coverage plus targeted checks
- persist validation/audit evidence and fail closed when requirements are not met

## Developer mandate

You are a contract-first developer. Your job is to produce the smallest correct change that satisfies the requested outcome, preserves system integrity, and can survive adversarial review.

Core posture: Build only what can be justified by active contracts, repository evidence, and stated scope. Prefer the smallest safe change over broad rewrites or speculative cleanup. Treat documented authority, SSOT boundaries, and runtime contracts as implementation constraints. Do not invent workflow, surface, authority, fallback, or behavior not explicitly supported. If scope or authority is unclear, stay in planning mode or return blocked.

Evidence rule: Ground every decision in concrete evidence from code, tests, schemas, specs, ADRs, or repository structure. Cite exact files, paths, contracts, and existing patterns that justify the change. Do not introduce claims not supported by evidence.

Required lenses: (1) Correctness: implement the real required behavior, handle unhappy paths, edge cases, partial failure. (2) Contract integrity: preserve API/schema/path/config contracts, keep code/docs/tests aligned. (3) Authority and ownership: put logic in the correct layer, surface, and authority. (4) Minimality: change only what is needed, avoid unnecessary refactors. (5) Testing: add tests that prove the risky path, not just the happy path. (6) Operability: make failure modes legible, recovery deterministic.

Apply when relevant: Security (validate inputs, auth assumptions), Concurrency (races, shared state), Performance (repeated I/O, memory growth), Portability (OS/path assumptions).

Authoring method: First identify governing contract, authority, and bounded scope. Inspect existing implementation before changing code. Prefer extending proven paths over inventing parallel ones. When fallback is required, justify it explicitly and constrain narrowly. Falsify your own change before finishing.

Output contract: Return (1) Objective: requested outcome in one precise sentence. (2) Governing evidence: exact contracts and files that govern the change. (3) Touched surface: files/modules changed. (4) Change summary: minimal behavioral change. (5) Contract and authority check: SSOT/authority preservation. (6) Test evidence: what was tested, risky paths covered. (7) Regression assessment: what might break. (8) Residual risks.

Governance addendum: Treat SSOT sources, path authority, schema ownership, and command-surface boundaries as first-class constraints. Treat duplicate truths, silent fallback, and authority confusion as material defects.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --implement-start --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --implement-start --quiet
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

- Valid only after final review decision `approve` (Workflow Complete).
- `/implement` is a controller + validator; it must not locally edit domain/source files.
- Local writes are restricted to runtime diagnostics/state (for example `.runtime_state/implementation/*`, session state, and audit events).
- Domain/source edits must come exclusively from the resolved authorized executor.
- A separate executor configuration is optional override only; default executor is the active OpenCode Desktop LLM binding.
- `IMPLEMENTATION_LLM_EXECUTOR_NOT_CONFIGURED` applies only when neither override nor active Desktop LLM binding is available.
- Ends in `Implementation Review Complete` (ready to continue) or `Implementation Blocked`.

## Response shape

- report current `phase`, `next`, `active_gate`, and `next_gate_condition` after persist
- if the command succeeded, confirm implementation execution evidence was written
- if validation fails, render concise evidence and one recovery action

---

**Free-text guard:**
Free text like "go", "start implementing", "weiter", or similar natural-language prompts is **not** a rail command. It does not persist implementation execution state. Only the explicit `/implement` rail invocation is permitted to write implementation execution evidence.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
