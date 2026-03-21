# Governance Review

## Purpose

`/review` is an independent, parallel review command for Phase 4. It lives alongside `/ticket` as its own workflow — it does not require ticket intake and does not depend on `/ticket` having been run. When the full governance bootstrap has been executed, `/review` has access to the complete repository context including repo discovery, architecture decisions, and business rules. This knowledge must inform the review.

`/review` is a read-only rail entrypoint for PR, file, or directory review. It does not perform implementation changes and does not reroute phase state. The review gate authority remains in the kernel (phase_api.yaml), not in the rail itself.

<!-- rail-classification: READ-ONLY, GATE-EVALUATION, NO-STATE-CHANGE -->

## Syntax

`/review <target>` where `<target>` is a PR URL (`https://github.com/owner/repo/pull/123`), GitLab MR, Bitbucket PR, file path (`src/main.py`), or directory path (`src/`).

## Execute

When governance execution is available, first read the materialized Session/Gate view (via `opencode-governance-bootstrap --session-reader`) to establish the phase and gate context. No state mutation occurs.

1. Fetch content: GitHub → `gh pr diff <N> --repo <owner>/<repo>`; GitLab → `glab mr diff <IID>`; Bitbucket → `bb pr <ID>`; local files → read directly.
2. Review with active LLM using this mandate:
```
REVIEW_MANDATE:
- Attempt to falsify before approving; do not assume correctness without evidence.
- Confirm only claims backed by code, contracts, tests, or explicit architecture policy.
- Actively check for contract drift, logic gaps, cross-OS risk, silent fallback leakage, and test gaps.
- Prefer fail-closed outcomes when evidence is incomplete.
```
Do not infer or mutate any session state.

## Scope

Cover these aspects based on what is changed, informed by the full repo context (repo discovery, architecture decisions, business rules, build conventions):

- **Correctness**: Does the code do what it claims? Does it match repo conventions?
- **Security**: Any authentication, authorization, or data exposure issues?
- **Testing**: Are there adequate tests? Do they follow repo test patterns?
- **Error Handling**: Are errors handled per repo conventions?
- **Performance**: Any obvious bottlenecks or inefficient patterns?
- **Maintainability**: Is the code easy to understand per repo standards?
- **Architecture**: Does it respect repo boundaries and dependencies?
- **API Contract**: Are contracts (internal or external) respected?
- **Regression Risk**: Could this break existing functionality?
- **Rollback Safety**: Can this change be safely reverted?
- **Contract Compliance**: Does it follow extracted business rules and policies?

Severity: HIGH (bugs, security, breaking changes) | MEDIUM (performance, missing tests) | LOW (style, minor improvements).

## Response

Produce a comprehensive review. Do not omit findings to be "nice" — adversarial review is the mandate.

- Verdict: `approve` or `changes_requested`
- Findings: `| # | Severity | Category | Location | Finding | Action |`
- Paste-ready: `<details><summary>Review Comments</summary>@author...findings...</details>`

## Commands by Platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader
```

## If execution is unavailable

If the command cannot be executed, paste the command output. If no snapshot is available, proceed using visible context and state assumptions explicitly. Minimum required snapshot fields: `phase`, `next`, `active_gate`, `next_gate_condition`.

Copyright © 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
