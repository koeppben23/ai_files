---
contract: rail-style-spec
version: v1
status: active
scope: Structural template and language constraints for execution-facing and bootstrap-facing markdown rails
owner: docs/governance/doc_lint.md
effective_version: 0.1.0
supersedes: null
conformance_suite: tests/test_rail_conformance_sweep.py
related: docs/contracts/cross-agent-rail-spec.v1.md
---

# Rail Style Spec — v1

> **Status:** active | **Scope:** Defines the mandatory block structure, platform command rules,
> placeholder policy, and banned language patterns for execution-facing and bootstrap-facing
> markdown rails. This spec builds on top of `cross-agent-rail-spec.v1.md` (CR-01 through CR-09).

## 1. Purpose

LLM agents from different model families (Anthropic Claude/Opus, OpenAI Codex, and others)
interpret execution instructions differently. This spec standardizes the internal structure
of command rails so that:

- Every execution-facing rail follows the same 5-block layout.
- Command blocks cover the platforms agents actually run on (bash, PowerShell).
- Fallback instructions are neutral and pressure-free.
- Placeholder and launcher conventions are explicit and testable.

### Guiding principle

> Functional command semantics, launcher targets, and free-text guards remain unchanged
> unless explicitly required by this spec.

## 2. Document Classification

Every markdown file in the repository belongs to exactly one of the following surface types.
This spec applies mandatory structural rules only to `execution-facing` and `bootstrap-facing`
files. The full conformance taxonomy (model-rail, hybrid, runbook, passive-doc) is defined
in `cross-agent-rail-spec.v1.md` Section 2 and remains authoritative for CR-01 through CR-09.

| Surface Type | Definition | Rail Style Spec Applicability |
|---|---|---|
| `execution-facing` | Command rails that an LLM invokes to materialize, mutate, or read governance state. Files: `continue.md`, `review.md`, `audit-readout.md`, `ticket.md`, `plan.md`, `review-decision.md` | **Full** — must implement all 5 mandatory blocks (Section 3) |
| `bootstrap-facing` | Onboarding/install rails that an LLM or user runs once to set up the governance environment. Files: `BOOTSTRAP.md` | **Structural** — must have Purpose, Commands by platform, and If execution unavailable blocks. Interpretation scope and Response shape are optional. |
| `guidance` | Behavioral guidance documents consumed by the LLM for cross-phase reasoning. Files: `master.md`, `rules.md` | **Not in scope** — reviewed separately under the guidance-language cleanup track |
| `passive-doc` | Reference docs, schemas, changelogs, READMEs — not LLM-directive | **Not in scope** — monitoring only |

## 3. Mandatory Block Structure (Execution-Facing Rails)

Every execution-facing rail must contain these 5 blocks, in order. Block headings are
not required to use the exact letters (A, B, C, D, E) but the content and sequence must
be present and identifiable.

### Block A — Purpose

State what the command does, what output to expect, and what to do if execution is impossible.

Requirements:
- One sentence describing the command's function.
- State whether the command is read-only or mutating.
- Do not use trust-triggering language (see Section 6).

### Block B — Commands by platform

Provide at least two fenced code blocks: one `bash`, one `powershell`.

Requirements:
- Execution-facing rails must provide bash and PowerShell command blocks.
- CMD is optional and only allowed when explicitly supported.
- Each code block must use the correct syntax for its platform (per CR-05).
- All command blocks must invoke the stable launcher name `opencode-governance-bootstrap` (per CR-06).
- Use `{{BIN_DIR}}` as the install-time-resolved placeholder for the binary directory (see Section 5).

### Block C — If execution is unavailable

Provide a neutral fallback for environments where shell execution is not possible.

Requirements:
- Do not use pressure-based tiering (Tier A / Tier B / Tier C) or prioritization labels.
- Use neutral phrasing: "If the command cannot be executed" or "If execution is unavailable".
- The fallback must specify one of:
  - "paste the command output", or
  - the minimum fields required: `phase`, `next`, `active_gate`, `next_gate_condition`.
- Include a degraded-mode statement for when no snapshot is available:
  "proceed using only the context visible in the current conversation and state assumptions explicitly."

### Block D — Interpretation scope

Constrain how the LLM uses the command output.

Requirements:
- State that only materialized output should be used; do not infer missing state.
- For read-only rails: explicitly state that no state mutation occurs.
- Reference the canonical schema or spec where the output format is defined.

### Block E — Response shape

Define what the LLM's response must contain after executing the command.

Requirements:
- List the required output fields or checklist items.
- Use the heading "Response shape" (not "Output checklist").
- Include at minimum: current phase, current gate, next action, and blockers (if any).

## 4. Bootstrap-Facing Block Structure

Bootstrap-facing files (`BOOTSTRAP.md`) must contain at minimum:

- **Purpose** — what the bootstrap/install does.
- **Commands by platform** — bash + PowerShell install blocks.
- **If execution is unavailable** — what to do if the installer cannot run.

The remaining blocks (Interpretation scope, Response shape) are optional for bootstrap files.

## 5. Placeholder and Launcher Rules

### 5.1 Allowed Placeholders

| Placeholder | Meaning | Resolution Time |
|---|---|---|
| `{{BIN_DIR}}` | Absolute path to the directory containing the governance launcher binary | Install-time (resolved by the installer and injected into rail files) |

`{{BIN_DIR}}` is an install-time-resolved placeholder. Execution-facing rails may use it
in command blocks. After installation, the placeholder is replaced with a platform-correct
absolute path to the binary directory.

### 5.2 Banned Primary Command Patterns

The following patterns are banned as primary command invocations in execution-facing rails:

| Pattern | Reason |
|---|---|
| User-specific absolute home paths (`$HOME/...`, `~/.config/...`, `/home/user/...`, `C:\Users\...`) | Non-portable; ties rails to a specific user's filesystem |
| Direct Python script calls (`python governance_runtime/entrypoints/...`, `python3 ...`, `py -3 ...`) when the stable launcher is available | Bypasses the launcher abstraction; fragile across environments |

## 6. Banned Language Patterns (Execution-Facing Rails)

These patterns are banned in execution-facing and bootstrap-facing rails. They extend
the CR-01/CR-02 banned patterns from `cross-agent-rail-spec.v1.md`.

| Banned Pattern | Replacement or Action |
|---|---|
| `safe to execute` | Remove entirely |
| `authoritative` (self-referential) | Use concrete SSOT reference or remove (per CR-02) |
| `kernel-owned` | Not permitted in execution-facing rails. Allowed only in guidance documents with SSOT pointer. |
| `installer guarantees` | Remove entirely |
| `Preferred (Tier A)` | Replace with neutral command introduction |
| `Fallback (Tier B)` | Replace with "If the command cannot be executed" |
| `Fallback (Tier C)` | Replace with "If no snapshot is available" |
| `must NEVER` cascades (4+ consecutive directive lines) | Already banned by CR-08; restructure into list or table |
| `if you refuse, ask the user to run this exact binary from this path` | Remove entirely |
| `always run this tool` / `if in doubt, run it` | Remove entirely; provide neutral command block |
| Bash-only command syntax in a Windows context | Add PowerShell block (per Block B) |

### Explicit repo rule

> Terms such as `kernel-owned` are disallowed in command rails and execution-facing model
> markdown. Guidance documents are reviewed separately under the guidance-language cleanup track.

## 7. Conformance Testing

### 7.1 Structural Assertions (per execution-facing rail)

Each execution-facing rail must pass:

1. **5-block presence** — all 5 blocks (Purpose, Commands by platform, If execution unavailable, Interpretation scope, Response shape) are present.
2. **Platform block count** — at least one `bash` and one `powershell` fenced code block.
3. **Launcher assertion** — launcher name `opencode-governance-bootstrap` is present; no direct `python …/entrypoints/…` calls.
4. **Fallback content assertion** — fallback contains either "paste the command output" or the minimum fields (`phase`, `next`, `active_gate`, `next_gate_condition`).
5. **No banned patterns** — none of the patterns from Section 6 appear.
6. **Response shape heading** — section heading is "Response shape" (not "Output checklist").

### 7.2 Bootstrap Assertions

Each bootstrap-facing rail must pass:

1. **Purpose block** present.
2. **Platform block count** — at least one `bash` and one `powershell` fenced code block.
3. **No empty headings** — every heading has content below it.
4. **No duplicate content blocks** — no install block appears twice verbatim.

### 7.3 Relationship to CR-07

CR-07 in `cross-agent-rail-spec.v1.md` defines the tiered fallback requirement. This spec
replaces the Tier A/B/C labeling with neutral equivalents. The functional requirement
(preferred command, execution-unavailable fallback, degraded fallback) remains the same.
Test assertions for CR-07 should match the neutral phrasing defined in this spec rather
than the original Tier A/B/C labels.

## 8. Versioning

This spec follows the same versioning convention as other contracts in `docs/contracts/`.
Breaking changes (new mandatory blocks, new banned patterns, reclassification of files)
require a version bump and migration notes.
