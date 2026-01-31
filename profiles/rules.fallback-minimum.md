# Fallback Minimum Profile

Purpose:
Provide a mandatory baseline when a target repository lacks explicit
standards (no CI, no test conventions, no documented build steps).

## Activation condition
This profile applies ONLY when no repo-local standards are discoverable.

## Mandatory baseline (MUST)
- Identify how to build and verify the project.
  If not present, propose and establish a minimal runnable baseline.
- Do not claim verification without executed checks or explicit justification.
- For non-trivial changes, introduce or recommend minimal automation (CI).

## Minimum verification (MUST)
At least one of:
- Unit tests for core logic changes
- Integration test for boundary changes when feasible
- Smoke verification (build + basic run) if tests are absent

## Documentation (MUST)
- Ensure build/test instructions exist (create minimal documentation if missing).
- Record non-trivial decisions in ADR.md or an equivalent mechanism.

## Quality heuristics (SHOULD)
- Deterministic behavior; no hidden mutable state.
- Coherent error handling; no silent failures.
- Logging at critical boundaries without leaking sensitive data.

## Portability (MUST when persisting)
Use platform-neutral storage locations as defined in rules.md.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# End of file — rules.fallback-minimum.md
