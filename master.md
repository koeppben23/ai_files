# MASTER PROMPT

consolidated, model-stable, hybrid-capable, pragmatic,
with architecture, contract, debt & QA gates

======================================================================
LAZY LOADING MODE (A)
======================================================================
- Phase 1–3: workflow + analysis ONLY (no core rules)
- Phase 4+: core + profile rules REQUIRED
- Phase 3 is analytical and MUST NOT require core rules
======================================================================

## PHASE 1: RULES LOADING (LAZY + ENHANCED)

### Phase 1.1: Minimal Bootstrap (IMMEDIATE)

LOAD IMMEDIATELY:
- master.md (this file)
- QUALITY_INDEX.md
- CONFLICT_RESOLUTION.md

SESSION_STATE bootstrap (binding):
SESSION_STATE.Phase = "1.1"
SESSION_STATE.Mode = "NORMAL"
SESSION_STATE.LoadedRulebooks = { core: "", profile: "" }
SESSION_STATE.ActiveProfile = ""
SESSION_STATE.ProfileSource = "deferred"
SESSION_STATE.ProfileEvidence = "deferred-until-phase-2"

Rationale:
- Phase 1–3 require only workflow, quality index and conflict resolution.
- No technical rules are needed before implementation planning.

----------------------------------------------------------------------
## PHASE 2: REPOSITORY DISCOVERY
----------------------------------------------------------------------

Purpose:
- Understand repository structure
- Detect technology signals
- Build RepoMapDigest

Outputs:
- RepoMapDigest
- Technology evidence
- Candidate profiles

----------------------------------------------------------------------
## PHASE 1.2: PROFILE DETECTION (POST-PHASE-2)
----------------------------------------------------------------------

TRIGGER:
- After Phase 2 completes

ACTION:
- Detect ActiveProfile from repo signals
- OR request explicit user selection if ambiguous
- Load profile rulebook

UPDATE:
SESSION_STATE.ActiveProfile
SESSION_STATE.ProfileSource
SESSION_STATE.ProfileEvidence
SESSION_STATE.LoadedRulebooks.profile

BLOCKING RULE:
- If multiple profiles exist and no scope or user decision is provided
  → BLOCKED

----------------------------------------------------------------------
## PHASE 3: ANALYTICAL VALIDATION (NO CORE RULES)
----------------------------------------------------------------------

Includes:
- API inventory
- Contract inspection
- Schema inspection
- Logical consistency checks

RULE:
- Phase 3 MUST NOT require rules.md
- Phase 3 MUST NOT generate code

----------------------------------------------------------------------
## PHASE 4: IMPLEMENTATION PLANNING (CORE RULES REQUIRED)
----------------------------------------------------------------------

TRIGGER:
- Any step that may result in code generation

ACTION:
- Load rules.md
- Merge with active profile rulebook

UPDATE:
SESSION_STATE.LoadedRulebooks.core

BLOCKING RULE (BINDING):
- If rules.md cannot be loaded at Phase 4
  → BLOCKED

----------------------------------------------------------------------
## PHASE 5: ARCHITECTURE & QUALITY GATES
----------------------------------------------------------------------

- Architecture compliance
- Test strategy validation
- Debt & rollback safety

----------------------------------------------------------------------
## PHASE 6: IMPLEMENTATION QA
----------------------------------------------------------------------

- Build evidence validation
- Deterministic gate decision

END OF MASTER PROMPT