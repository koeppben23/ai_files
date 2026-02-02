# Ticket Record Template (Mini-ADR + NFR Checklist)

Use this template for **every ticket** to make trade-offs explicit and reduce cognitive load.
Keep it compact; the goal is **fast, reviewable clarity**, not a full design doc.

---

## Ticket
- **ID:** <optional>
- **Title:** <one line>

## Ticket Record (Mini-ADR) — 5–10 lines max
- **Context:** <1 line>
- **Decision:** <1 line>
- **Rationale:** <1 line>
- **Consequences:** <1 line>
- **Rollback/Release safety:** <feature flag / backout steps / reversible migration / “no rollback needed”>
- **Open questions:** <optional>

## Architecture Options (A/B/C) — required when decision surface is non-trivial
- **Decision to make:** <one line>
- **Option A:** <one line> — <trade-offs (perf/complexity/operability/risk)> — <test impact>
- **Option B:** <one line> — <trade-offs (perf/complexity/operability/risk)> — <test impact>
- **Option C:** <optional>
- **Recommendation:** <A|B|C> (confidence <0–100>) — <why> — <what evidence could change the decision>

## NFR Checklist (one line each)
- **Security/Privacy:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Observability:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Performance:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Migration/Compatibility:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Rollback/Release safety:** <OK|N/A|Risk|Needs decision> — <1 sentence>

## Test Strategy (short, plan-ready)
- **Levels:** <unit|slice|integration|contract> — <what each level proves>
- **Determinism:** <time/clock, randomness, IDs, external I/O seams>
- **Fixtures/Builders:** <what will be reused/added; where it lives>
- **Edge cases:** <boundary + negative case at least>

---

Tip: If a decision is **non-trivial** and likely to matter beyond this ticket, also record it in `ADR.md`.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
