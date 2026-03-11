# Architecture Decision Records (ADR)

This file stores **explicit architecture decisions** made during work with this governance system.

Goals:
- Reduce cognitive load (decisions don’t live only in chat history)
- Preserve architectural intent over time
- Enable conflict detection (new proposals vs. existing decisions)

Rules of thumb:
- Record only **non-trivial** decisions (things that affect architecture, contracts, boundaries, persistence, deployment, security posture, or major dependencies).
- Keep entries short, structured, and evidence-linked when possible.

---

## ADR-0001: <Title>

- **Date:** YYYY-MM-DD
- **Status:** accepted | superseded | deprecated
- **Context:** (what problem are we solving; constraints)
- **Decision:** (what we chose)
- **Options considered:**
  - A)
  - B)
- **Rationale:** (why this choice)
- **Trade-offs:** (what we give up)
- **Evidence:** (repo paths, tickets, diagrams; if available)
- **ConfidenceLevel:** 0-100 (aligns with master.md session state)
- **Re-evaluation criteria:** (what would make us revisit this)

---

## ADR-0001: Canonical Operating Profiles

- **Date:** 2026-03-11
- **Status:** accepted
- **Context:** Runtime mode handling had legacy tokens (`user|pipeline|agents_strict|system`) and lacked a canonical governance profile contract for precedence, floors, and trusted enforcement.
- **Decision:** Introduce canonical profiles `solo|team|regulated` with deterministic monotonic resolution (`solo < team < regulated`) and explicit trust-boundary checks for runtime enforcement.
- **Options considered:**
  - A) Keep legacy mode tokens as the only contract
  - B) Add canonical profile contract with alias bridge (chosen)
- **Rationale:** Canonical profiles make policy/audit semantics stable while preserving backward compatibility through alias mapping.
- **Trade-offs:** Runtime internals still expose legacy effective mode values; profile-to-runtime mapping is intentionally conservative until full surface migration.
- **Evidence:** `governance/domain/operating_profile.py`, `governance/application/use_cases/resolve_operating_mode.py`, `governance/engine/mode_repo_rules.py`, `tests/test_operating_profile_resolution.py`
- **ConfidenceLevel:** 87
- **Re-evaluation criteria:** Revisit once runtime surfaces and response contracts can emit canonical profile fields end-to-end without legacy aliases.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — ADR.md
