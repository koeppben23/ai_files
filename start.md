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

**Informational (kernel-enforced):**
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

**Informational (kernel-enforced):**

Identity evidence boundary (informational):
- Helper output is operational convenience status only and is not canonical repo identity evidence.
- Repo identity is governed by `master.md` evidence contracts (host-collected git evidence, operator-provided evidence, or prior validated mapping/session state).

Bootstrap preflight and evidence semantics (informational):
- `/start` may collect git identity evidence and command availability diagnostics before bootstrap completes.
- Binding evidence uses installer-owned `${COMMANDS_HOME}/governance.paths.json` as canonical source.
- Fallback computed payloads remain debug-only (`nonEvidence`).
- Blocked reasons, gate decisions, and recovery commands are kernel-managed (see `diagnostics/bootstrap_policy.yaml` and `diagnostics/blocked_reason_catalog.yaml`).

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

### Discovery / Load search order (informational)

> **Note:** Discovery roots, evidence precedence, and fail-closed behavior are kernel-enforced.
> See `diagnostics/bootstrap_policy.yaml` for canonical roots, evidence sources, and gate definitions.

Search paths (informational):
- `${COMMANDS_HOME}/master.md`
- `${COMMANDS_HOME}/rules.md`
- `${PROFILES_HOME}/rules.<profile>.md` OR `${PROFILES_HOME}/rules_<profile>.md` OR `${PROFILES_HOME}/rules-<profile>.md`

### Evidence rule (informational)

> **Note:** Evidence collection and fail-closed behavior are kernel-enforced.
> See `diagnostics/bootstrap_policy.yaml` (gates: binding_file_gate, start_evidence_gate).

Evidence sources (informational):
- Host-provided file access evidence (preferred)
- Installer recovery (fallback when host evidence unavailable)

Blocked reasons (kernel-enforced):
- BLOCKED-MISSING-BINDING-FILE (missing governance.paths.json)
- BLOCKED-START-REQUIRED (missing /start evidence)

Invocation:
- Activate the Governance-OS defined in `master.md`.
- This file does not replace or inline `master.md`; it only triggers its discovery and activation.

> **Note:** Bootstrap gates, evidence requirements, and blocked reasons are kernel-enforced.
> See `diagnostics/bootstrap_policy.yaml` and `diagnostics/blocked_reason_catalog.yaml`.

Key behaviors (informational):
- `/start` is mandatory bootstrap for a repo/session (kernel-enforced).
- Missing evidence or profile ambiguity may result in blocked state (kernel-enforced).
- Profile selection is deferred to Phase 1.2/Post-Phase-2 (kernel-enforced).
- During Phase `1.5/2/2.1/3A/3B`, no task/ticket is required; ticket goal required only at Phase 4 entry (kernel-enforced).

Rulebook discovery (informational):
- Rulebooks are loaded from canonical locations (`${COMMANDS_HOME}`, `${PROFILES_HOME}`).
- If rulebooks are unavailable, operator provides evidence (path or content).
- Canonical expected locations:
  - master.md: `${COMMANDS_HOME}/master.md`
  - rules.md: `${COMMANDS_HOME}/rules.md`
  - profiles: `${PROFILES_HOME}/rules*.md`

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
