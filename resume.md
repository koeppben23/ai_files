RESUME — Controlled Session Continuation (Guidance)

Use these references as guidance context:
- master.md
- rules.md
- SCOPE-AND-CONTEXT.md
- the active profile rulebook referenced by SESSION_STATE.ActiveProfile (e.g., rules.backend-java.md)

Kernel/config remain authoritative for runtime routing and gate decisions.

The provided `SESSION_STATE` is the primary continuity artifact for response context.

Profile guidance:
- If `SESSION_STATE.ActiveProfile` is missing or ambiguous, surface the uncertainty explicitly and request clarification.
- For planning-only turns, keep output stack-neutral when profile evidence is missing.

Response guidance:
- Avoid re-discovery unless explicitly requested.
- Keep phase and gate references aligned with current `SESSION_STATE` evidence.
- Avoid introducing new domain/architecture assumptions.
- Preserve prior decisions unless new evidence is provided.
- Keep implementation output consistent with current gate posture.

When continuing, align response context with:
SESSION_STATE.Phase
SESSION_STATE.Gates
SESSION_STATE.Next

If `SESSION_STATE` is missing, incomplete, or inconsistent, clearly report missing context and request the minimal information needed.

Acknowledge loaded context and continue with the operator's requested next step.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
