# Governance Review

<!-- rail-classification: READ-ONLY, GATE-EVALUATION, NO-STATE-CHANGE -->

## Purpose

`/review` is an independent, parallel review command for Phase 4. It lives alongside `/ticket` as its own workflow — it does not require ticket intake and does not depend on `/ticket` having been run. However, `/review` requires `/hydrate` to be executed first to bind the governance session to the OpenCode session and establish the knowledge base context.

When the full governance bootstrap has been executed AND `/hydrate` has been run, `/review` has access to the complete repository context including repo discovery, architecture decisions, and business rules. This knowledge must inform the review.

`/review` is a read-only rail entrypoint for PR, file, or directory review. It does not perform implementation changes and does not reroute phase state. The review gate authority remains in the kernel (phase_api.yaml), not in the rail itself.

Binding mode is authoritative per `governance-config.json` and mode-scoped:
- `pipeline_mode=false` (default): use the active OpenCode chat binding.
- `pipeline_mode=true`: require explicit review binding via `AI_GOVERNANCE_REVIEW_BINDING` and fail closed if missing/empty.

## Syntax

`/review <target>` where `<target>` is a PR URL (`https://github.com/owner/repo/pull/123`), GitLab MR, Bitbucket PR, file path (`src/main.py`), or directory path (`src/`).

## Execute

**Prerequisite: Hydration Required** — Fail-closed.

1. Read session snapshot via `opencode-governance-bootstrap --session-reader`
2. Check `session_hydrated` field
3. **If NOT hydrated**: Block and do no review work. Return: `blocked: session-not-hydrated. Run /hydrate first.`
4. **If hydrated**: Proceed with review below.

When governance execution is available, first read the materialized Session/Gate view (via `opencode-governance-bootstrap --session-reader`) to establish the phase and gate context.

1. Fetch content: GitHub → `gh pr diff <N> --repo <owner>/<repo>`; GitLab → `glab mr diff <IID>`; Bitbucket → `bb pr <ID>`; local files → read directly.
2. Apply the Review mandate below — falsification-first, evidence-only, fail-closed.
3. Return structured findings: verdict (approve or changes_requested), findings table, paste-ready PR comments.

Do not infer or mutate any session state.

## Binding contract

- Review role binding variable: `AI_GOVERNANCE_REVIEW_BINDING`.
- Execution role binding variable (for planning/implementation flows): `AI_GOVERNANCE_EXECUTION_BINDING`.
- In direct mode (`pipeline_mode=false`), env bindings are ignored.
- In pipeline mode (`pipeline_mode=true`), review must use `AI_GOVERNANCE_REVIEW_BINDING` as the authoritative review role binding; no fallback to active chat binding.
- No mixing: direct mode does not consume env bindings; pipeline mode does not use active chat binding as substitute.
- For production reproducibility, prefer explicit stable binding references over drifting aliases.

## Review mandate

The canonical Review mandate is defined in `governance_content/reference/rules.md` (SSOT). Read it before executing. The runtime executor loads the compiled mandate from `governance_runtime/assets/schemas/governance_mandates.v1.schema.json` (derived artifact — never edit directly).

## Commands by Platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader
```

## If execution is unavailable

If the command cannot be executed, paste the command output. If no snapshot is available, proceed using visible context and state assumptions explicitly. Minimum required snapshot fields: `phase`, `next`, `active_gate`, `next_gate_condition`.

## Response shape

- give a clear verdict aligned to final decision tokens: `approve` or `changes_requested`
- list findings with severity and one concrete action per finding
- provide paste-ready PR comments (one per blocker/high + one summary)

Quality bar:
- prefer high-signal findings over stylistic noise
- focus on correctness, risk, and release safety first
- keep feedback actionable and specific to changed surfaces
Copyright © 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
