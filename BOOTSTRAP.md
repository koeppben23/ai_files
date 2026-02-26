# Bootstrap Guide

This document describes how to bootstrap the OpenCode Governance System for a repository.

## Overview

The OpenCode Governance System ensures consistent development practices across repositories. Before working in a repository, you must run the bootstrap process to activate governance.

## Bootstrap Process

The bootstrap process:

1. **Validates binding** - Checks `governance.paths.json` exists
2. **Detects repository** - Finds Git root and computes fingerprint
3. **Creates workspace** - Sets up `SESSION_STATE.json`
4. **Applies gates** - Ensures all required gates are satisfied

## Standard Bootstrap Path

The recommended way to bootstrap is using the **local launcher**:

### macOS / Linux

```bash
~/.config/opencode/bin/opencode-governance-bootstrap
```

### Windows

```cmd
%USERPROFILE%\.config\opencode\bin\opencode-governance-bootstrap.cmd
```

## Installation First

If the launcher is not available, run the installer first:

```bash
python3 install.py
```

This creates:
- Configuration directory at `~/.config/opencode`
- Commands and governance files
- Local bootstrap launcher
- Workspace directories

## Verification

After bootstrap, verify success by checking:

```bash
cat ~/.config/opencode/workspaces/<fingerprint>/SESSION_STATE.json
```

The file should contain:
- `Phase`: "4" or higher
- `Bootstrap.Satisfied`: `true`
- `PersistenceCommitted`: `true`

## Troubleshooting

### "Invalid or missing binding file"

Run the installer:
```bash
python3 install.py
```

### "Repository root not found"

Provide the repository path:
```bash
opencode-governance-bootstrap --repo-root /path/to/repo
```

Or ensure you're in a Git repository.

## Documentation

- `master.md` - Core governance rules
- `rules.md` - Implementation guidelines
- `profiles/` - Profile-specific rulebooks

## Kernel Enforcement Notes

Bootstrap gates, evidence requirements, and blocked reasons are kernel-enforced via `governance/assets/config/bootstrap_policy.yaml`.

Discovery / Load search order (informational)
- `governance/assets/config/bootstrap_policy.yaml`

Fallback computed payloads remain debug-only (`nonEvidence`).
Helper output is operational convenience status only and is not canonical repo identity evidence.

## Response Contract Requirements

At session start, include exactly one start-mode banner based on discovery artifact validity evidence:
- `[START-MODE] Cold Start - reason:`
- `[START-MODE] Warm Start - reason:`

Include `[SNAPSHOT]` block (`Confidence`, `Risk`, `Scope`) with values aligned to current `SESSION_STATE`.

`SESSION_STATE` output MUST be formatted as fenced YAML (````yaml` + `SESSION_STATE:` payload)
`SESSION_STATE` output MUST NOT use placeholder tokens (`...`, `<...>`); use explicit unknown/null values instead

End every response with `[NEXT-ACTION]` footer (`Status`, `Next`, `Why`, `Command`) per `master.md` (also required in COMPAT mode)
`[NEXT-ACTION]` footer MUST include `PhaseGate` (`phase | active_gate | phase_progress_bar`) for quick phase orientation.
Render `[NEXT-ACTION]` as multiline footer (one line per field); do not emit a single pipe-joined line.

If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`) when host constraints allow
If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `["none"]` if not command-driven) when host constraints allow.

If strict output formatting is host-constrained, response MUST include COMPAT sections: `RequiredInputs`, `Recovery`, and `NextAction` and set `DEVIATION.host_constraint = true`.
Response mode MUST be explicit and singular per turn: `STRICT` or `COMPAT`.
`STRICT` requires envelope + `[SNAPSHOT]` + `[NEXT-ACTION]`; `COMPAT` requires `RequiredInputs` + `Recovery` + `NextAction` + `[NEXT-ACTION]`.

## Additional Contract Tokens

Bootstrap process
Bootstrap preflight and evidence semantics (informational):
- governance/assets/config/bootstrap_policy.yaml
- governance/assets/reasons/blocked_reason_catalog.yaml

Responses SHOULD include a compact `status_tag` for scanability (`<PHASE>-<GATE>-<STATE>`).
Responses SHOULD include `phase_progress_bar` (for example: `[##----] 2/6`) aligned to the current phase.
Responses MUST include compact phase progress from `SESSION_STATE`: `phase`, `active_gate`, `next_gate_condition`.

Status vocabulary MUST remain deterministic: `BLOCKED | WARN | OK | NOT_VERIFIED`.
`WARN` MUST NOT be used when required-gate evidence is missing
`WARN` may include `advisory_missing` only and MUST NOT emit blocker `RequiredInputs`.
Exactly one `NextAction` mechanism is allowed per response
If blocked, use exactly one `reason_code`, one concrete recovery action sentence, and one primary copy-paste command.

`NextAction` wording SHOULD include concrete context (active phase/gate/scope) rather than generic continuation text.
On phase/mode changes, response SHOULD include a compact transition line: `[TRANSITION] <from> -> <to> | reason: <short reason>`.
If no phase/mode/gate transition occurred, response SHOULD acknowledge `state_unchanged` with a concise reason.
For no-change turns, response SHOULD be delta-only (or explicit `no_delta`) instead of repeating unchanged governance.

When `QuickFixCommands` are emitted, the bootstrap flow SHOULD label primary command confidence as `safe` or `review-first`.
`QuickFixCommands` defaults to one command; use two only for explicit `macos_linux` vs `windows` splits.
The bootstrap flow SHOULD use `governance/assets/catalogs/QUICKFIX_TEMPLATES.json` for reason-code-specific recovery command text when available.
If multiple blockers exist, the bootstrap flow SHOULD present one `primary_reason_code` first and keep one primary recovery command.

Across lifecycle transitions, `session_run_id` and `ruleset_hash` remain stable unless explicit rehydrate/reload is performed (kernel-enforced).
Every phase/mode transition records a unique `transition_id` diagnostic entry (kernel-enforced).

Short follow-up questions SHOULD route via deterministic intents (`where_am_i`, `what_blocks_me`, `what_now`) before optional verbose governance.
Conversational post-start replies SHOULD stay covered by deterministic fixture intents (`what_phase`, `discovery_done`, `workflow_unchanged`).
Preferred conversational fixture source: `governance/assets/catalogs/UX_INTENT_GOLDENS.json`.

When preparing a PR that changes governance contracts, response SHOULD include an operator-impact section (`What changed for operators?`).
Governance PR summaries SHOULD also include `Reviewer focus` bullets for highest-risk contract deltas.
Response persona modes SHOULD be supported (`compact`, `standard`, `audit`) as presentation-density controls only.
