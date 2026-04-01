---
description: Read-only audit readout of governance session state, chain integrity, and last snapshot.
---

# Governance Audit Readout

<!-- rail-classification: READ-ONLY, OUTPUT-ONLY, NO-STATE-CHANGE -->

## Context

This command is part of a **locally installed governance extension** for OpenCode.
It is not a native OpenCode core feature.  The governance runtime, its command
rails, and all referenced files reside in the local OpenCode configuration
directory as part of the project's governance setup.

## Purpose

`/audit-readout` is a read-only rail entrypoint.
The command below prints an `AUDIT_READOUT_SPEC.v1` JSON payload and does not modify any files.
It reports `active`, `last_snapshot`, `chain`, and `integrity` per the `AUDIT_READOUT_SPEC.md` contract.

## Commands by platform

```bash
PATH="{{BIN_DIR}}:$PATH" opencode-governance-bootstrap --session-reader --audit --tail-count 25
```

```powershell
$env:Path = "{{BIN_DIR}};" + $env:Path; opencode-governance-bootstrap --session-reader --audit --tail-count 25
```

## If execution is unavailable

If the command cannot be executed, ask the user to paste the command output.

If no snapshot is available, proceed using only the context visible in the current conversation and state assumptions explicitly.

## Interpretation scope

Use the JSON output as audit context for the response below. Do not infer additional state beyond the materialized output.

## Response shape

- include `contract_version`
- include `active.run_id`, `active.phase`, and `active.active_gate`
- include `last_snapshot.snapshot_path` and `last_snapshot.snapshot_digest`
- include `integrity.snapshot_ref_present`, `integrity.run_id_consistent`, and `integrity.monotonic_timestamps`
- if an integrity flag is false, provide concise evidence and one recovery action

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
