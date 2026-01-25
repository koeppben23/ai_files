RESUME — Controlled Session Continuation

Load and strictly enforce:
- master.md
- rules.md
- SCOPE-AND-CONTEXT.md
- the active profile rulebook referenced by SESSION_STATE.ActiveProfile (e.g., rules.backend-java.md)

The SESSION_STATE provided by the user is the single authoritative source of truth.

Profile rule:
- If SESSION_STATE.ActiveProfile is missing or ambiguous: switch to BLOCKED mode and request it; do not assume a default profile.
- Exception (planning-only): If the user explicitly requests planning/analysis only (no code, no file edits), you may proceed in Phase 4 without an ActiveProfile and must remain stack-neutral.

Rules:
- Do NOT re-run discovery
- Do NOT change phases
- Do NOT introduce new domain/architecture assumptions; only record administrative assumptions (e.g., missing metadata) if explicitly marked as such.
- Do NOT reinterpret past decisions
- Do NOT introduce new assumptions
- Do NOT generate code unless explicitly allowed by the current gate state

Continue execution strictly according to:
SESSION_STATE.Phase
SESSION_STATE.Gates
SESSION_STATE.Next

If the SESSION_STATE is missing, incomplete, or inconsistent:
- Switch to BLOCKED mode
- Request the missing information
- Do NOT proceed

Acknowledge the loaded SESSION_STATE and wait for further instruction.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
