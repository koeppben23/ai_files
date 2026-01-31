# Conflict Resolution & Priority Model

Purpose:
Define deterministic resolution of conflicting instructions to prevent
oscillation and ambiguity.

## Priority order (highest → lowest)

P0: Safety, legality, non-negotiable constraints
P1: Session phases and gates
    (master.md; SESSION_STATE_SCHEMA.md)
P2: Evidence and scope bounding rules
    (SCOPE-AND-CONTEXT.md; SESSION_STATE_SCHEMA.md)
P3: Repository-local mandatory rules
    (e.g. AGENTS.md, CI requirements, enforced tooling)
P4: Active profile rules
    (profiles/*)
P5: Global governance rules
    (rules.md; README-RULES.md)
P6: Preferences, heuristics, stylistic guidance

## Resolution rule
- In case of conflict, the higher-priority source MUST be followed.
- Any overridden lower-priority instruction MUST be explicitly noted,
  including the reason and the governing higher-priority reference.

## Hard vs Soft
- Hard rules: P0–P3 and any rule marked MUST.
- Soft rules: SHOULD/MAY guidance and stylistic preferences.

## Output requirement
Conflicts MUST NOT be hidden.
Emit a short "Conflict note" when a conflict occurs.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# End of file — CONFLICT_RESOLUTION.md
