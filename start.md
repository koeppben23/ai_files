# Governance Start

This is the bootstrap entrypoint for the governance system.

## Purpose

`/start` initiates the governance workflow by:
1. Validating binding evidence
2. Running preflight checks
3. Loading core governance files
4. Establishing session state

## Binding Evidence

`/start` requires binding evidence from `${COMMANDS_HOME}/governance.paths.json`.
If missing: returns `BLOCKED-MISSING-BINDING-FILE` with recovery command.

## Preflight

Preflight checks probe required commands and report availability.
Results determine whether governance proceeds normally or in degraded mode.

Bootstrap gates, evidence requirements, and blocked reasons are kernel-enforced.
See `governance/assets/config/bootstrap_policy.yaml` and `governance/assets/reasons/blocked_reason_catalog.yaml`.

Helper output is operational convenience status only and is not canonical repo identity evidence.

Fallback computed payloads remain debug-only (`nonEvidence`).

## Start Modes

- **Cold Start**: No valid session artifacts found
- **Warm Start**: Valid session artifacts exist

Start mode is determined by artifact presence and validity evidence.

## After Start

After successful bootstrap:
- Workflow continues automatically to first user-facing stop
- Operator receives phase/gate status
- Next action is communicated clearly

## Blocked States

If blocked, response includes:
- Reason code
- Missing evidence
- Recovery steps

---

This file is AI-facing guidance. Runtime control remains kernel-owned.
Boundary reference: `docs/governance/RESPONSIBILITY_BOUNDARY.md`

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
