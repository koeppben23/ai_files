# User Max Quality Rulebook

This document defines the maximum quality enforcement contract for user mode.
It is a required addon that enforces rigorous output standards without relying on automated tooling.

## Intent (binding)

Enforce the highest quality standards for implementation tasks through:
- Required output sections that force thorough documentation
- Verification handshake requiring explicit human confirmation
- Risk-tier triggers for additional scrutiny on high-risk surfaces
- Claim verification preventing silent assumptions

## Scope (binding)

All implementation tasks in user mode where quality is paramount.
This addon is required; code output is prohibited until all required sections are present.

Precedence (binding): use the canonical order from `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.
As a required addon, this rulebook MUST be loaded before code output is permitted.

## Activation (binding)

Activation is manifest-owned via `profiles/addons/userMaxQuality.addon.yml`.
This rulebook defines behavior after activation and MUST NOT redefine activation signals.

## Phase integration (binding)

- Phase 2: verify quality contract awareness, initialize output section checklist
- Phase 2.1: enforce required output sections for architecture decisions
- Phase 4: verify test matrix completeness, edge cases documented
- Phase 5: enforce verification handshake for all claims
- Phase 5.3: verify risk-tier triggers evaluated for touched surfaces
- Phase 6: final verification handshake, all claims marked with status

## Evidence contract (binding)

- Maintain `SESSION_STATE.AddonsEvidence.userMaxQuality.status` (`loaded|skipped|missing-rulebook`).
- Required addons prohibit code output until loaded: `BLOCKED-MISSING-ADDON:userMaxQuality`.
- All output sections MUST be documented in `SESSION_STATE.AddonsEvidence.userMaxQuality.OutputSections`.

## Tooling (binding)

This addon is tooling-agnostic by design:
- Verification commands are specified by the user/implementation context
- No automated tooling is required; human verification is mandatory
- When host tooling is available, use it for evidence collection
- When tooling is unavailable, mark claims as `NOT_VERIFIED` with manual verification steps

---

## Quality Contract (Binding)

### Required Output Sections (User Mode)

When this addon is active, ALL implementation tasks MUST produce:

1. **Intent & Scope** - What is being built and why
   - Clear problem statement
   - User-facing value
   - Success criteria

2. **Non-goals** - What is explicitly out of scope
   - Features not implemented
   - Edge cases deferred
   - Technical debt accepted

3. **Design/Architecture** - Structural decisions with rationale
   - Component diagram (text or ASCII)
   - Data flow description
   - Key interfaces/contracts

4. **Invariants & Failure Modes** - What must always/never happen
   - Pre-conditions
   - Post-conditions
   - Invariants
   - Known failure modes and handling

5. **Test Plan (Matrix)** - Coverage strategy by test type
   - Unit test scope
   - Integration test scope
   - Contract test scope (if applicable)
   - Manual verification steps

6. **Edge Cases Checklist** - Boundary conditions and corner cases
   - Empty inputs
   - Maximum inputs
   - Invalid inputs
   - Concurrent access (if applicable)
   - Network failures (if applicable)

7. **Verification Commands** - Exact commands for human execution
   - Build command
   - Test command(s)
   - Lint/typecheck command(s)
   - Manual verification steps

8. **Risk Review** - NPE/leaks/concurrency/security analysis
   - Null pointer risks
   - Resource leak risks
   - Thread safety risks
   - Security considerations

9. **Rollback Plan** - How to undo if deployment fails
   - Database rollback (if applicable)
   - Feature flag toggle
   - Configuration revert
   - Monitoring/verification steps

### Verification Handshake (Binding)

Verified status requires explicit human confirmation:

```
LLM Output: "Verification Commands: [cmd1, cmd2, ...]"
Human Response: "Executed [cmd1]: [result1]; Executed [cmd2]: [result2]"
LLM: Set `Verified` only after receiving results; otherwise mark `NOT_VERIFIED`
```

Protocol:
1. LLM lists all verification commands
2. Human executes and reports results
3. LLM marks `Verified` only with evidence
4. Without evidence, mark `NOT_VERIFIED` with recovery steps

### Risk-Tier Triggers (Binding)

When touched files match risk surfaces, this addon MUST require additional scrutiny:

| Risk Surface | Trigger Patterns | Additional Requirements |
|--------------|------------------|------------------------|
| Persistence/Pointer | `*Repository*`, `*DAO*`, `*Mapper*`, `*Entity*`, `*.sql`, `*pointer*` | NPE audit, Leak audit, Rollback plan |
| Security/Auth | `*Auth*`, `*Security*`, `*Token*`, `*Password*`, `*Permission*`, `*Key*` | Threat model checklist, Input validation audit |
| Concurrency | `*Thread*`, `*Async*`, `*Concurrent*`, `*Lock*`, `*Mutex*`, `*Queue*` | Thread-safety audit, Race condition checklist |
| External APIs | `*Client*`, `*Api*`, `*Http*`, `*Request*`, `*Response*`, `*External*` | Contract tests, Timeout handling, Retry logic |

Risk-Tier Protocol:
1. Scan touched files against trigger patterns
2. Identify all matching risk surfaces
3. Document additional requirements in Risk Review section
4. Verify additional requirements are addressed before marking Verified

### Claim Verification (Binding)

All claims MUST follow these rules:

- **ASSUMPTION** marker: Required for any assumption made
  - Example: `ASSUMPTION: Database connection pool size is 10`
  - Example: `ASSUMPTION: API rate limit is 1000 req/min`

- **NOT_VERIFIED** marker: Required for any claim not yet executed
  - Example: `NOT_VERIFIED: Tests pass (not executed)`
  - Example: `NOT_VERIFIED: Performance is acceptable (no benchmarks run)`

- **Language/Version**: Must be explicit with rationale
  - BAD: "Use Python"
  - GOOD: "Use Python 3.11 for pathlib improvements and type hinting enhancements"

---

## Shared Principal Governance Contracts (Binding)

This addon delegates to shared governance contracts:

- `rules.principal-excellence.md` - Principal-grade review criteria
- `rules.risk-tiering.md` - Risk tier classification
- `rules.scorecard-calibration.md` - Scorecard evaluation

Tracking keys (audit pointers, not activation logic):
- `SESSION_STATE.LoadedRulebooks.addons.principalExcellence`
- `SESSION_STATE.LoadedRulebooks.addons.riskTiering`
- `SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration`

---

## Examples (GOOD/BAD)

### GOOD: Complete Output Section

```markdown
## Intent & Scope
Add user registration with email verification.

## Non-goals
- Social login (Phase 2)
- Password reset (Phase 2)

## Design/Architecture
UserService -> EmailService -> TokenRepository
Token expires after 24h (configurable).

## Invariants & Failure Modes
- Invariant: Email must be unique
- Failure: Email send fails -> queue for retry

## Test Plan
- Unit: UserService.register(), TokenRepository.create()
- Integration: Full registration flow
- Manual: Verify email received

## Edge Cases
- Duplicate email (reject with message)
- Invalid email format (validate before send)
- Token expired (allow resend)

## Verification Commands
```bash
pytest tests/unit/test_user_service.py
pytest tests/integration/test_registration.py
```

## Risk Review
- Persistence: TokenRepository uses JPA, no NPE risk
- Security: Token is cryptographically random
- External: Email service has timeout + retry

## Rollback Plan
1. Disable feature flag `USER_REGISTRATION_V2`
2. No DB migration to revert
```

### BAD: Incomplete Output Section

```markdown
## Intent
Add user registration.

## Test Plan
Tests will be written.

## Risk Review
Looks safe.
```

This is missing: Non-goals, Design, Invariants, Edge Cases, Verification Commands (no actual commands), Rollback Plan.

## Troubleshooting

1) Symptom: BLOCKED-MISSING-ADDON:userMaxQuality
- Cause: Addon not loaded before code-phase
- Fix: Ensure `profiles/addons/userMaxQuality.addon.yml` exists and is referenced in profile

2) Symptom: Output sections incomplete despite requirements
- Cause: Template not followed or sections skipped
- Fix: Re-run implementation with explicit section-by-section checklist

3) Symptom: NOT_VERIFIED claims remain at Phase 6
- Cause: Verification handshake not completed
- Fix: Execute verification commands and report results to LLM

4) Symptom: Risk-tier triggers not evaluated
- Cause: Touched files not scanned against patterns
- Fix: Scan all touched files and document matching risk surfaces

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
