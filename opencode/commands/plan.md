# Governance Plan

<!-- rail-classification: MUTATING, GATE-EVALUATION -->

## Purpose

`/plan` is the productive planning rail. It generates a plan from the persisted ticket/task, runs self-review, and persists the result.
The command is mutating — it writes evidence and reroutes kernel state.

**Auto-generation (default):** When no `--plan-text` or `--plan-file` is provided, `/plan` reads the ticket and task from session state and generates a structured plan via mode-aware governance binding. The generated plan is reviewed (max 3 self-review iterations) and only persisted when valid.

**Explicit input:** You may also provide plan text directly via `--plan-text` or `--plan-file`. In this case only the generation step is skipped; the mandatory self-review loop still uses the resolved governance review binding.

Deterministic plan flow:
1. read Ticket/Task from session state
2. load plan mandate and effective policy (fail-closed)
3. LLM generates structured plan (conforms to planOutputSchema)
4. self-review loop (max 3 iterations)
5. compile to requirement contracts
6. persist plan-record evidence
7. reroute state

## Commands

Auto-generation (reads Ticket/Task from session state):

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --plan-persist --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --plan-persist --quiet
```

Explicit plan text input (skips LLM generation):

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --plan-persist --plan-text "<plan text>" --quiet
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --plan-persist --plan-text "<plan text>" --quiet
```

## Binding contract

Binding mode is authoritative per `governance-config.json` and mode-scoped:

- `pipeline_mode=false` (default): planning and internal self-review use the active OpenCode chat binding.
- `pipeline_mode=true`: planning uses `AI_GOVERNANCE_EXECUTION_BINDING`; internal self-review uses `AI_GOVERNANCE_REVIEW_BINDING`.

Rules:

- In direct mode, env bindings are ignored.
- In pipeline mode, missing/empty required binding is fail-closed.
- No mixing: pipeline mode does not fall back to active chat binding.
- For production reproducibility, prefer explicit stable binding references over drifting aliases.

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output or a snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`.
If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Response shape

- report `phase`, `next`, `active_gate`, `next_gate_condition` after persist; confirm evidence written and state rerouted on success
- emit final governance readout after successful persist — do not stop at raw JSON output; if blocker/warning present, render with evidence and one recovery action
- when `plan_under_review_summary` is present, **you must** render a **Plan** section containing exactly that preview (max 6 lines, max 800 chars); never skip this section
- **always** end with exactly one `Next action:` line as the final output line — no additional text after it

---

**Free-text guard (Fix 1.4b):**
Free-text like "go", "weiter", "proceed", "mach weiter", or any other natural-language prompt is **not** a rail command. It does not trigger the plan persist command above, `/continue`, or any state write. Only the explicit `/plan` rail invocation is permitted to persist Phase-5 plan-record evidence. If the user sends free-text that implies plan submission, ask them to invoke `/plan` explicitly.
