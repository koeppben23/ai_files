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

## NFR Checklist (one line each)
- **Security/Privacy:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Observability:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Performance:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Migration/Compatibility:** <OK|N/A|Risk|Needs decision> — <1 sentence>
- **Rollback/Release safety:** <OK|N/A|Risk|Needs decision> — <1 sentence>

---

Tip: If a decision is **non-trivial** and likely to matter beyond this ticket, also record it in `ADR.md`.

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.
