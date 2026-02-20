# Governance Start — master invocation

This project uses a formal LLM Governance System
defined in `master.md`, `rules.md`, and profile rulebooks.

Invariant checklist for regression prevention: `docs/governance_invariants.md`.


## Auto-Binding Evidence (OpenCode)

Bootstrap Evidence: OpenCodeBinding (governance.paths.json + preflight) OR AGENTS.md Presence (Codex surface).
Note: Kernel remains the source of truth; AGENTS.md is the Codex frontend surface.

When executed as an OpenCode command (`/start`), this prompt injects the installer-owned path binding file
`${COMMANDS_HOME}/governance.paths.json` into the model context.

**Implementation Reference:** The OpenCode host executes `${COMMANDS_HOME}/diagnostics/start_binding_evidence.py`
to resolve binding evidence. This script is part of the kernel and implements the binding resolution logic.

**Policy (this document):**
- If binding file exists at `${COMMANDS_HOME}/governance.paths.json`:
  - Load and validate binding evidence
  - Proceed with bootstrap
- If binding file missing:
  - Return `BLOCKED-MISSING-BINDING-FILE`
  - Provide recovery command: `${PYTHON_COMMAND} install.py`

## Auto-Preflight Hook (OpenCode, Read-only)

When available, `/start` triggers a read-only diagnostics preflight helper.
This helper MUST NOT write workspace/index/session artifacts.
Persistence and workspace readiness are kernel-owned only.

**Implementation Reference:** The OpenCode host executes `${COMMANDS_HOME}/diagnostics/start_preflight_readonly.py`
to perform preflight checks. This script is part of the kernel and implements the preflight logic.

**Policy (this document):**

Identity evidence boundary (binding):
- Helper output is operational convenience status only and MUST NOT be treated as canonical repo identity evidence.
- Repo identity remains governed by `master.md` evidence contracts (host-collected git evidence, operator-provided evidence, or prior validated mapping/session state).

Identity discovery order (binding):
- If host shell tools are available and the current workspace is a git repository, `/start` MUST collect repo identity evidence first via non-destructive git commands (`git remote get-url origin`, `git symbolic-ref refs/remotes/origin/HEAD`, `git rev-parse --show-toplevel`) before requesting operator-provided evidence.
- If host-side git discovery is unavailable or fails, `/start` MUST block with identity-missing reason and provide copy-paste recovery commands.

Bootstrap command preflight (binding):
- `/start` MUST check required external commands in `PATH` first (at minimum: `git`, `${PYTHON_COMMAND}` when diagnostics helpers are used).
- `/start` MUST load command requirements from `${COMMANDS_HOME}/diagnostics/tool_requirements.json` when available.
- If `diagnostics/tool_requirements.json` is unavailable, `/start` MUST derive the command list by scanning canonical governance artifacts (`master.md`, `rules.md`, `profiles/rules*.md`, `diagnostics/*.py`) and classify it into `required_now`, `required_later`, and `optional`.
- `/start` MUST print the resolved command inventory and probe result (`available`/`missing`) before requesting operator action.
- Preflight diagnostics are informational and MUST NOT create a blocker by themselves.
- If all required commands are present, `/start` should report `preflight: ok` and continue without interruption.
- If commands are missing, `/start` should report `preflight: degraded` with missing command names and copy-paste install/recovery hints; block only if a downstream gate cannot be satisfied without the missing command.
- If a missing command is installed later, rerunning `/start` MUST recompute the inventory from files and continue with refreshed PATH evidence.
- Preflight MUST run in Phase `0` / `1.1`, with fresh probe signals only (`ttl=0`) and `observed_at` timestamp.
- Preflight output MUST stay compact (max 5 checks) and use fixed keys: `available`, `missing`, `impact`, `next`.
- Preflight output SHOULD separate `required_now` vs `required_later` and expose a deterministic `block_now` signal (`true` iff any `required_now` command is missing).
- Missing-command diagnostics MUST include `expected_after_fix`, `verify_command`, and `restart_hint`.
- `restart_hint` MUST be deterministic: `restart_required_if_path_edited` or `no_restart_if_binary_in_existing_path`.

Binding evidence semantics (binding):
- Only an existing installer-owned `${COMMANDS_HOME}/governance.paths.json` qualifies as canonical binding evidence.
- Fallback computed payloads are debug output only (`nonEvidence`) and MUST NOT be treated as binding evidence.
- If installer-owned binding file is missing, workflow MUST block with `BLOCKED-MISSING-BINDING-FILE`.
- Canonical binding location is `${USER_HOME}/.config/opencode/commands/governance.paths.json`.

---

## Governance Evidence — Variable Resolution (Binding)

This entrypoint MUST NOT contain OS-specific absolute paths.
All locations MUST be expressed using canonical variables as defined by `master.md`.

Clarification (Binding):
- "This entrypoint" refers ONLY to the `start.md` file content.
- Operator-provided evidence MAY include OS-specific absolute paths when supplied as chat input,
  because they are evidence about the runtime environment, not persisted governance text.

### Required variables (conceptual)
- `${USER_HOME}` (OS-resolved user home)
- `${CONFIG_ROOT}` (OpenCode config root = `${USER_HOME}/.config/opencode`)
- `${OPENCODE_HOME} = ${CONFIG_ROOT}`
- `${COMMANDS_HOME} = ${OPENCODE_HOME}/commands`
- `${PROFILES_HOME} = ${COMMANDS_HOME}/profiles`

### Discovery / Load search order (Binding)
The runtime MUST attempt to resolve rulebooks using this search order:
1) `${COMMANDS_HOME}/master.md`
2) `${COMMANDS_HOME}/rules.md`
3) `${PROFILES_HOME}/rules.<profile>.md` OR `${PROFILES_HOME}/rules_<profile>.md` OR `${PROFILES_HOME}/rules-<profile>.md`

Runtime resolution scope note (binding):
- `/start` enforces installer-owned discovery roots (`${COMMANDS_HOME}`, `${PROFILES_HOME}`) as canonical entrypoint requirements.
- Workspace/local overrides and global fallbacks (`${REPO_OVERRIDES_HOME}`, `${OPENCODE_HOME}`) are runtime resolution extensions governed by `master.md` and MUST NOT weaken this entrypoint contract.

### Evidence rule (Binding)
Because this file cannot self-prove filesystem state, governance activation MUST use one of:

A) **Host-provided file access evidence** (preferred)
   - Tool output showing the resolved directory listing for `${COMMANDS_HOME}` and `${PROFILES_HOME}`, OR
   - Tool output confirming reads of `master.md` (and top-tier bootstrap artifacts when present); `rules.md` load evidence is deferred until Phase 4.

Binding behavior (MUST):
- If installer-owned `${COMMANDS_HOME}/governance.paths.json` exists and host filesystem tools are available,
  `/start` MUST attempt host-provided evidence first and MUST NOT request operator-provided variable binding before that attempt.

B) **Installer recovery required** (fallback)
   - If host-provided evidence cannot be loaded, `/start` MUST fail closed and instruct installer recovery.
   - `/start` MUST NOT ask the operator to manually resolve `${COMMANDS_HOME}` via chat input.

If neither A nor installer recovery is available -> `BLOCKED` with required input = "Run installer repair and rerun /start".
Canonical BLOCKED reason:
- BLOCKED-MISSING-BINDING-FILE (missing `${COMMANDS_HOME}/governance.paths.json` at canonical location)

Invocation:
- Activate the Governance-OS defined in `master.md`.
- This file does not replace or inline `master.md`; it only triggers its discovery and activation.
- Command invocation guard (binding): when `start.md` is injected by the `/start` command, treat `/start` as already invoked in this turn.
- In that case, assistant MUST NOT request the operator to run `/start` again unless an explicit hard failure indicates command context was not injected.
- During `/start`, assistant MUST NOT ask generic task-intake questions (for example, "what task do you want me to handle?") before bootstrap evidence/gates finish.
- Phases 1–6 are enforced as far as host/system constraints allow.
- `/start` is mandatory bootstrap for a repo/session.
- In hosts that support `/master`: `/master` without valid `/start` evidence MUST map to `BLOCKED-START-REQUIRED` with `QuickFixCommands: ["/start"]`.
- OpenCode Desktop mapping (host-constrained): `/start` acts as the `/master`-equivalent and performs the ARCHITECT master-run inline.
- Canonical operator lifecycle (OpenCode Desktop): `/start` (bootstrap + ARCHITECT master-run) -> `Implement now` (IMPLEMENT) -> `Ingest evidence` (VERIFY).
- Plan-Gates ≠ Evidence-Gates.
- Missing evidence → BLOCKED (reported, not suppressed).
- Profile ambiguity → BLOCKED.
- `/start` MUST NOT require explicit profile selection to complete bootstrap when `master.md` bootstrap evidence is available; profile selection remains a Phase 1.2/Post-Phase-2 concern.
- If multiple profile rulebooks exist, `/start` attempts deterministic repo-signal autodetection first and auto-selects when one candidate is uniquely supported (kernel-enforced).
- During Phase `1.5/2/2.1/3A/3B`, `/start` does not require a task/ticket to proceed; ticket goal is required only at Phase 4 entry (kernel-enforced).
- If current phase is `3A`/`3B-*`/`4`/`5*` and operator asks `Reopen Phase 1.5`, `/start` allows explicit re-entry to `1.5-BusinessRules` and marks BusinessRules compliance for rerun before final readiness (kernel-enforced).
- When profile signals are ambiguous, provide a ranked profile shortlist with evidence and request explicit numbered selection (`1=<recommended> | 2=<alt> | 3=<alt> | 4=fallback-minimum | 0=abort/none`) before activation.

Rulebook discovery contract (BINDING):
- The assistant MUST NOT claim `master.md`, `rules.md`, or profile rulebooks are "missing"
  unless it has explicit load evidence that lookup was attempted in the canonical locations
  OR the operator confirms the files are not present.
- If rulebook contents are not available in the current chat context, treat them as
  `NOT IN PROVIDED SCOPE` and request minimal evidence (path or pasted content).
- If host filesystem access is available and profile detection is unambiguous, `/start` MUST auto-load canonical rulebooks and MUST NOT request operator rulebook paste/path input.
- If Business Rules file write is unavailable, `/start` MUST keep `${REPO_BUSINESS_RULES_FILE}` as target and MUST NOT redirect to `${WORKSPACE_MEMORY_FILE}`.
- Canonical expected locations (per master.md variables):
  - master.md: `${COMMANDS_HOME}/master.md`
  - rules.md: `${COMMANDS_HOME}/rules.md`
  - profiles: `${PROFILES_HOME}/rules*.md`
- If the host cannot access the filesystem, the operator MUST provide one of:
  A) exact resolved paths + confirmation they exist, OR
  B) paste the full file contents for master.md (bootstrap minimum); defer rules.md/profile rulebook contents to their phase gates (rules.md: Phase 4, profile: Phase 2 detection).

Host constraint acknowledgment:
- Host / system / developer instructions may override this governance.
- Any such override MUST be reported explicitly under `DEVIATION`
  (rule/gate + best conforming alternative).

Output requirements:
- Structured, phase-oriented output
- Operator-first layering SHOULD be used: concise brief first (status + phase/gate + one next step), then detailed diagnostics
- After successful bootstrap, short follow-up answers SHOULD be conversational and language-adaptive to operator input unless full diagnostics are requested.
- Conversational post-start replies SHOULD stay covered by deterministic fixture intents (`what_phase`, `discovery_done`, `workflow_unchanged`).
- Preferred conversational fixture source: `diagnostics/UX_INTENT_GOLDENS.json`.
- Short follow-up questions SHOULD route via deterministic intents (`where_am_i`, `what_blocks_me`, `what_now`) before optional verbose diagnostics.
- Response persona modes SHOULD be supported (`compact`, `standard`, `audit`) as presentation-density controls only.
- Output envelope SHOULD comply with `diagnostics/RESPONSE_ENVELOPE_SCHEMA.json` (`status`, `session_state`, `next_action`, `snapshot`; plus blocker payload fields when blocked) when host constraints allow
- STRICT/COMPAT output matrix SSOT is defined in `master.md` and `rules.md`; this file mirrors entrypoint-specific expectations only.
- `next_action.type` MUST be present and one of: `command`, `reply_with_one_number`, `manual_step`.
- Status vocabulary MUST remain deterministic: `BLOCKED | WARN | OK | NOT_VERIFIED`.
- `WARN` MUST NOT be used when required-gate evidence is missing (that case MUST be `BLOCKED`).
- Responses MUST include compact phase progress from `SESSION_STATE`: `phase`, `active_gate`, `next_gate_condition`.
- Responses SHOULD include `phase_progress_bar` (for example: `[##----] 2/6`) aligned to the current phase.
- Responses SHOULD include a compact `status_tag` for scanability (`<PHASE>-<GATE>-<STATE>`).
- If no phase/mode/gate transition occurred, response SHOULD acknowledge `state_unchanged` with a concise reason.
- For no-change turns, response SHOULD be delta-only (or explicit `no_delta`) instead of repeating unchanged diagnostics.
- `WARN` may include `advisory_missing` only and MUST NOT emit blocker `RequiredInputs`.
- Explicit SESSION_STATE
- In STRICT envelopes, `session_state` MAY be a compact machine-readable snapshot object.
- `SESSION_STATE` output MUST be formatted as fenced YAML (````yaml` + `SESSION_STATE:` payload)
- In this section, the YAML requirement applies to dedicated full-state `SESSION_STATE` blocks (including explicit diagnostics/full-state output), not to the compact strict-envelope snapshot projection.
- When full `SESSION_STATE` is emitted as a dedicated state block, it MUST be formatted as fenced YAML (````yaml` + `SESSION_STATE:` payload)
- `SESSION_STATE` output MUST NOT use placeholder tokens (`...`, `<...>`); use explicit unknown/deferred values instead
- Explicit Gates
- Explicit DEVIATION reporting
- Prefer structured (non-chat) answers when host constraints allow
- End every response with `[NEXT-ACTION]` footer (`Status`, `Next`, `Why`, `Command`) per `master.md` (also required in COMPAT mode)
- `[NEXT-ACTION]` footer MUST include `PhaseGate` (`phase | active_gate | phase_progress_bar`) for quick phase orientation.
- Render `[NEXT-ACTION]` as multiline footer (one line per field); do not emit a single pipe-joined line.
- Exactly one `NextAction` mechanism is allowed per response: `command` OR `reply_with_one_number` OR `manual_step`.
- `NextAction` wording SHOULD include concrete context (active phase/gate/scope) rather than generic continuation text.
- If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`) when host constraints allow
- If multiple blockers exist, `/start` SHOULD present one `primary_reason_code` first and keep one primary recovery command.
- If blocked, use exactly one `reason_code`, one concrete recovery action sentence, and one primary copy-paste command.
- `next_command` and `QuickFixCommands` SHOULD be fully runnable without placeholders when runtime evidence can derive concrete values.
- Across lifecycle transitions, `session_run_id` and `ruleset_hash` remain stable unless explicit rehydrate/reload is performed (kernel-enforced).
- Every phase/mode transition records a unique `transition_id` diagnostic entry (kernel-enforced).
- On phase/mode changes, response SHOULD include a compact transition line: `[TRANSITION] <from> -> <to> | reason: <short reason>`.
- At session start, include `[START-MODE] Cold Start | Warm Start - reason: ...` based on discovery artifact validity evidence.
- Include `[SNAPSHOT]` block (`Confidence`, `Risk`, `Scope`) with values aligned to current `SESSION_STATE`.
- If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `["none"]` if not command-driven) when host constraints allow.
- When `QuickFixCommands` are emitted, `/start` SHOULD label primary command confidence as `safe` or `review-first`.
- `/start` SHOULD use `diagnostics/QUICKFIX_TEMPLATES.json` for reason-code-specific recovery command text when available.
- `QuickFixCommands` defaults to one command; use two only for explicit `macos_linux` vs `windows` splits.
- If strict output formatting is host-constrained, response MUST include COMPAT sections: `RequiredInputs`, `Recovery`, and `NextAction` and set `DEVIATION.host_constraint = true`.
- Response mode MUST be explicit and singular per turn: `STRICT` or `COMPAT`.
- `STRICT` requires envelope + `[SNAPSHOT]` + `[NEXT-ACTION]`; `COMPAT` requires `RequiredInputs` + `Recovery` + `NextAction` + `[NEXT-ACTION]`.
- If operator requests full details (for example: `show diagnostics`, `show full session state`), `/start` SHOULD emit full strict diagnostics without changing gate/evidence outcomes.
- Default strict rendering SHOULD emit a compact `SESSION_SNAPSHOT` projection and avoid full-session dumps unless diagnostics intent is explicit.
- Compact snapshot SHOULD include stable decision references (`activation_hash`; optionally `ruleset_hash`) and compact drift context (`state_unchanged` / `no_delta`) when available.
- Full `SESSION_STATE` remains required as canonical persisted state; compact rendering is a view-layer projection only.
- Session-state rollout posture is final: phase >= 3 is engine-only legacy-removed mode; legacy alias compatibility is historical only and MUST NOT be used as a normal-path dependency.
- Recovery command integrity: emitted recovery commands MUST reference existing artifacts/scripts; if a specific helper is unavailable, fail closed and emit one minimal real command (default: `/start`).
- When preparing a PR that changes governance contracts, response SHOULD include an operator-impact section (`What changed for operators?`).
- Governance PR summaries SHOULD also include `Reviewer focus` bullets for highest-risk contract deltas.

This file is the canonical governance entrypoint.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — start.md
