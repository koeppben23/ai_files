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
- `/implement` is a controller + validator; it must not locally edit domain/source files.
- Local writes are restricted to runtime diagnostics/state (for example `.runtime_state/implementation/*`, session state, and audit events).
- Domain/source edits must come exclusively from the resolved authorized executor.
- A separate executor configuration is optional override only; default executor is the active OpenCode Desktop LLM binding.
- `IMPLEMENTATION_LLM_EXECUTOR_NOT_CONFIGURED` applies when neither override nor active Desktop LLM binding is available.
- In shell/bootstrap subprocess mode, governance first attempts a callable Desktop bridge via `opencode-cli run` using the active session model binding. If no callable bridge binary is available, fail closed with `IMPLEMENTATION_LLM_EXECUTOR_NOT_CONFIGURED` and set `OPENCODE_IMPLEMENT_LLM_CMD`.
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
