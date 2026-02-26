# AGENTS (rails-only, non-normative)

This file is a **non-normative** integration surface for agent/front-end tools.

**SSOT lives in the engine + locked configs** (engine master policy, pack-lock, mode-policy, host permissions, repo-doc constraints).

If anything conflicts: **engine/configs win** (kernel wins).

## Start gate (must be fail-closed)

Do not proceed past bootstrap unless workspace persistence is committed:
- SESSION_STATE.json exists in the fingerprint workspace
- `PersistenceCommitted=true`
- `WorkspaceReadyGateCommitted=true`

If missing: run the equivalent of `/start` and stop.

## Default operating posture

- Plan-first (ARCHITECT) unless explicit "Implement now".
- No claim without evidence recorded in SESSION_STATE; otherwise NOT_VERIFIED.
- Deterministic execution only; fail-closed on missing bindings/packs/permissions.

## Scope

- This file must not introduce new requirements.
- No host-specific paths, tokens, or binding instructions here.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — AGENTS.md
