# /audit — Self-Audit & Diagnostics (Read-Only)

## PURPOSE (Descriptive)
Run a deterministic, read-only diagnostics pass over the current session.
This command MUST NOT:
- change phases
- modify files
- generate code
- bypass gates
- invent missing evidence

If any instruction here conflicts with `master.md` or `rules.md`, treat this file as wrong.

---

## INPUTS (Expected)
- Current `[SESSION_STATE]` (canonical form as defined in `master.md`)
- Any current ticket / scope context already in session
- Any repo discovery artifacts already recorded in session (if repo-aware mode)

If `[SESSION_STATE]` is missing, the command MUST stop with `BLOCKED` and request it.

---

## OUTPUT FORMAT (Mandatory)

Return exactly these sections, in this order:

1. `[AUDIT_REPORT]` header line
2. Phase & Gate Trace
3. Rule Resolution Trace
4. Evidence Coverage Audit
5. Scope & Inputs Audit
6. Config / Paths Audit (repo-aware only; otherwise "NOT APPLICABLE")
7. Confidence Ceiling
8. Allowed Next Actions (minimal, safe)
9. `[END_AUDIT_REPORT]`

No extra sections.

---

## 1) AUDIT HEADER

Print:

[AUDIT_REPORT]
Timestamp=<ISO8601>
Mode=<chat-only|repo-aware>
SessionPhase=<...>
Degraded=<active|inactive>
Confidence=<0-100%>

---

## 2) PHASE & GATE TRACE (Mandatory)

Derive from `SESSION_STATE` and the rules:

- Current Phase
- Active gates for this phase (as defined by `master.md` + `rules.md`)
- Gate statuses (pending/pass/blocked/not-applicable)
- If blocked: name EXACT blocking gate(s) and show:
  - GateKey
  - Status
  - BlockingReasonKey (existing key from `master.md` if available; else "UNSPECIFIED")
  - RequiredEvidence / RequiredInput (list)

Rules:
- If the current phase implies gates but gate status is missing, treat as `BLOCKED` with reason `BR_MISSING_SESSION_GATE_STATE`.

---

## 3) RULE RESOLUTION TRACE (Mandatory)

List, in order, which sources are currently authoritative and active:

- master.md (always)
- rules.md (active or not, and why)
- active profile rulebook (if any) and why it was selected
- active addons/templates (if any) and why

For each, print:
- SourceType=<master|rules|profile|addon>
- Path=<...>
- Status=<loaded|not-loaded|not-applicable>
- ActivationReason=<phase|evidence|explicit|fallback|unknown>

Rules:
- Do NOT infer unknown profile/addon selection. If unknown, print `unknown` and mark `BLOCKED` with `BR_MISSING_RULEBOOK_RESOLUTION`.

---

## 4) EVIDENCE COVERAGE AUDIT (Mandatory)

Report presence/absence of key evidence categories, based ONLY on session artifacts:

- Repo discovery evidence (present/absent)
- Business rules extraction (executed/not-executed/not-applicable)
- Change Matrix (present/absent)
- Contract/schema checks (present/absent/not-applicable)
- Test execution evidence (present/absent/theoretical-only)
- Diff/patch evidence (present/absent)

Rules:
- If an item is required by the current phase/gate and missing → mark `BLOCKED` and point to the gate.
- Do NOT substitute theory for evidence; label as "theoretical-only".

---

## 5) SCOPE & INPUTS AUDIT (Mandatory)

Report whether the session has explicit scope and required inputs:

- Ticket goal (present/absent)
- ComponentScope (present/absent if applicable)
- External contracts (OpenAPI/events) (present/absent/not-applicable)
- DB schema/migrations (present/absent/not-applicable)
- Non-functional constraints (present/absent)

Rules:
- If scope lock requires an artifact and it is missing → `BLOCKED` with reason `BR_SCOPE_ARTIFACT_MISSING`.

---

## 6) CONFIG / PATHS AUDIT (Repo-aware only)

If Mode=repo-aware, evaluate configuration validity using existing `master.md` rules:

- Is CONFIG_ROOT set?
- Are derived paths consistent (COMMANDS_HOME, PROFILES_HOME, WORKSPACES_HOME)?
- Any degenerate path detected? (e.g., "C", "C:", "rules.md", "business-rules.md")
- Any repo-local write attempts recorded?

Rules:
- If any blocked condition applies, print:
  - BLOCKED_REASON_KEY=<...>
  - ObservedValue=<...>
  - ExpectedConstraint=<...>

If Mode=chat-only, print:
Config/Paths Audit: NOT APPLICABLE

---

## 7) CONFIDENCE CEILING (Mandatory)

Compute a strict ceiling from missing evidence:

- Start from current Confidence in SESSION_STATE (if present)
- Cap based on missing evidence categories:
  - No executed tests → cap <= 70%
  - No business rules when required → cap <= 65%
  - No change matrix when required → cap <= 60%
  - No repo discovery in repo-aware required phases → cap <= 55%
  - Missing session state / missing rule resolution → cap = 0% (blocked)

Print:
ConfidenceCeiling=<...>
CeilingReasons:
- ...

Rules:
- Never raise confidence above SESSION_STATE. Only cap down.

---

## 8) ALLOWED NEXT ACTIONS (Mandatory)

Provide 1–5 minimal safe actions that do not bypass gates.
Each action MUST be:
- specific
- evidence-producing
- phase-appropriate

Format:
AllowedNextActions:
1. ...
2. ...

Do NOT propose implementation steps if any gate is blocked for implementation.

---

## 9) AUDIT FOOTER

Print:
[END_AUDIT_REPORT]

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — audit.md
