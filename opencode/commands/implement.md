# Governance Implement

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/implement` starts execution of the approved implementation plan after approved Phase 6 governance review.
The command is mutating and must execute implementation work, not only preparation.

Binding mode is authoritative and mode-scoped:
- `pipeline_mode=false` (default): use the active OpenCode chat binding.
- `pipeline_mode=true`: require explicit environment binding and fail closed if missing.

`/implement` executes the approved plan with mode-aware binding resolution:
- load approved plan, hotspots, constraints, and required checks
- write execution input context (`.runtime_state/implementation/llm_edit_context.json`)
- resolve execution binding by mode:
  - direct mode: active OpenCode chat binding
  - pipeline mode: `AI_GOVERNANCE_EXECUTION_BINDING` (required)
- invoke implementation through the resolved execution binding (the only actor allowed to change domain files)
- run internal implementation self-review (validation-only; no local domain edits)
- collect git diff evidence and validate plan-coverage plus targeted checks
- persist validation/audit evidence and fail closed when requirements are not met

## Binding contract

- `AI_GOVERNANCE_EXECUTION_BINDING` is the execution/planning role binding.
- `AI_GOVERNANCE_REVIEW_BINDING` is the review role binding (internal review and Phase-4 review).
- In direct mode (`pipeline_mode=false`), both environment bindings are ignored.
- In pipeline mode (`pipeline_mode=true`), both bindings are required for governance flows; missing/empty binding is fail-closed.
- No mixing: direct mode does not consume env bindings; pipeline mode does not fall back to active chat binding.
- For production reproducibility, prefer explicit stable binding references over drifting aliases.

## Developer mandate

The canonical Developer mandate is defined in `governance_content/reference/rules.md` (SSOT). Read it before executing. The runtime executor loads the compiled mandate from `governance_runtime/assets/schemas/governance_mandates.v1.schema.json` (derived artifact — never edit directly).

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
- `/implement` is an execution action + validator; it must not locally edit domain/source files.
- Local writes are restricted to runtime diagnostics/state (for example `.runtime_state/implementation/*`, session state, and audit events).
- Domain/source edits must come exclusively from the resolved authorized execution binding.
- Validation uses execution-attributed change evidence (pre/post delta plus hotspot file hash changes) to avoid counting unrelated pre-existing dirty files as implementation output.
- Direct mode uses active chat binding and ignores `AI_GOVERNANCE_EXECUTION_BINDING`.
- Pipeline mode requires `AI_GOVERNANCE_EXECUTION_BINDING` for execution and `AI_GOVERNANCE_REVIEW_BINDING` for governance review flows; missing required binding fails closed with `IMPLEMENTATION_LLM_EXECUTOR_NOT_CONFIGURED`.
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
