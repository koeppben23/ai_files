# Mode-Aware Repo Rules + Host-Permissions Orchestration

This document defines deterministic handling for repository docs (for example `AGENTS.md`) under the governance engine.

## Invariants

- Repo docs are non-normative inputs and cannot override kernel policy.
- No silent escalation: widening write/command scope requires explicit approval and audit events.
- All mode decisions emit machine-readable reason payloads and precedence events.

## Precedence Order

1. Engine master policy (`master.md`)
2. Pack-lock + activation ruleset policy
3. Mode policy (`user`, `pipeline`, `agents_strict`)
4. Host permissions (OpenCode host config / CI runtime)
5. Repo-doc constraints (`AGENTS.md` and related docs)

When a lower layer conflicts with a higher layer, the higher layer wins and the engine emits `POLICY-PRECEDENCE-APPLIED`.

## Approval Authority Matrix

| Approval Type | user | agents_strict | pipeline |
| --- | --- | --- | --- |
| PlanApproval | User | User | Never |
| ScopeApproval | User | User | Never |
| CommandSetApproval | User | User | Never |
| WideningApproval | User (optionally User+Reviewer) | User (optionally User+Reviewer) | Never |
| PRApproval | User (optional) | User (optional) | Never |

Hard rule: pipeline mode has zero prompts and zero approvals; interactive-required steps block with `INTERACTIVE-REQUIRED-IN-PIPELINE`.

## Prompt Budgets (Hard Gates)

- `user`: `max_total_prompts=3`, `max_repo_doc_prompts=0`
- `agents_strict`: `max_total_prompts=10`, `max_repo_doc_prompts=6`
- `pipeline`: `max_total_prompts=0`, `max_repo_doc_prompts=0`

Budget exceed always blocks with `PROMPT-BUDGET-EXCEEDED`.

## Repo-Doc Classification

Repo-doc directives are classified into:

- `constraint`
- `interactive_directive`
- `unsafe_directive`

Unsafe directives block all modes with `REPO-DOC-UNSAFE-DIRECTIVE`.

## Evidence and Audit Artifacts

Runs emit deterministic artifacts:

- `repo_doc_evidence` (path, hash, classification summary)
- `precedence_events` (`POLICY-PRECEDENCE-APPLIED`)
- `prompt_events` (`PROMPT_REQUESTED` and related accounting events)

## Reason Registry Integration

Mode-aware reason codes and payload schemas are defined in:

- `diagnostics/reason_codes.registry.json`
- `diagnostics/schemas/reason_payload_*.v1.json`
