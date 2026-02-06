# README-RULES.md

## 📌 README Index

This document explains the intent and structure of the rules.
It does not override or redefine them.

- **Normative system authority and phase gates**  
  → See `master.md`

- **Actual enforceable rules**  
  → See `rules.md`

- **Context- and stack-specific extensions**  
  → See `profiles/*`

  Addons are discovered declaratively via addon manifests:
  → See `profiles/addons/*.addon.yml`

- **Operational usage and configuration**  
  → See `README-OPENCODE.md`

This README is explanatory only.

**Executive Summary for AI-Assisted Development**

This document is a **compact, non-normative overview** of the binding rules defined in **rules.md** and the **Master Prompt**.
The full technical requirements are defined in **rules.md** (plus the active profile rulebook, if any).
Operational AI behavior (phases, hybrid mode, priorities, session state) is defined in the **Master Prompt**.

This document contains **no standalone rules**.
It only summarizes the requirements defined in **rules.md**.
When in doubt, **rules.md** and the **Master Prompt** always take precedence.

Conflicts between sources are resolved deterministically via `CONFLICT_RESOLUTION.md`
(located next to `master.md`).

---

## 1. Purpose

### This process enables AI-assisted creation of:

* technical designs
* backend implementations
* API-based integrations
* unit / slice / integration tests
* traceability and quality evidence

All work follows a clearly structured, controlled workflow.

---

## 2. Mandatory Artifacts

### Archive Artifacts

All repositories, APIs, or collections of multiple files must be delivered as **archive artifacts**.

Examples (non-exhaustive):

* ZIP
* TAR
* TAR.GZ / TGZ
* TAR.BZ2 / TAR.XZ
* 7Z
* RAR

**Scope Lock:**
The AI may only access artifacts that were provided in the ticket or the current session.

---

## 3. Archive Artifacts – Mandatory Extraction

All provided archive artifacts must **always be extracted fully and for real** by the AI.

* Without successful extraction, **no** statements about contents, structures, or classes may be made.
* Heuristic, experience-based, or reconstructed inferences are not allowed.
* An archive that cannot be extracted is treated as **non-existent under the scope lock**.

---

## 4. Workflow (Collapsed View)

The full workflow consists of **6 phases** (including sub-phases and gates) as defined in the **Master Prompt**.
This document provides a **reduced 4-phase view** for quick orientation.

| Collapsed Phase           | Master Prompt Equivalent           |
| ------------------------- | ---------------------------------- |
| Phase A – Analysis        | Phase 1 + 2 + 2.1                  |
| Phase B – Solution Design | Phase 3A + Phase 3B-1              |
| Phase C – Validation      | Phase 3B-2 + Phase 4               |
| Phase D – Implementation  | Phase 5 (+ 5.6 in-gate) + 5.3 + optional (5.4/5.5) + 6 |

**Extended (with Business Rules Discovery):**

| Collapsed Phase           | Master Prompt Equivalent                                 |
| ------------------------- | -------------------------------------------------------- |
| Phase A – Analysis        | Phase 1 + Phase 2 + Phase 2.1 + *1.5 (optional)*         |
| Phase B – Solution Design | Phase 3A + Phase 3B-1                                    |
| Phase C – Validation      | Phase 3B-2 + Phase 4                                     |
| Phase D – Implementation  | Phase 5 (+ 5.6 in-gate) + *5.4 (if 1.5 was active)* + 5.5 (optional) + 6 |

**Important:**
All **gates, sub-phases (e.g., 3B-1 / 3B-2), and constraints** apply in full,
even if not listed individually in this collapsed view.

**Business Rules Discovery (Phase 1.5):**

* Executed when explicitly requested by the user, or after the Phase 2.1 A/B decision if not explicitly requested/skipped.
* Explicit skip signals include: "Skip business-rules discovery" and "This is a pure CRUD project".
* Recommendation for the A/B decision is evidence-based (Phase 2 signals), but execution still requires user approval.
* Extracts business rules from code / database / tests
* Reduces business-logic gaps from ~50% to <15%
* See Master Prompt Phase 1.5 for details

---

## 5. Hybrid Mode

The AI may switch flexibly between phases.

### Implicit Activation

* Ticket without prior artifacts → start directly in Phase 4
* Repository upload → start in Phase A
* API upload → start in Phase A

### Explicit Overrides

The following commands override all default rules:

* “Start directly in Phase 4.”
* “Skip Phase A.”
* “Work only on backend and ignore APIs.”
* “Use the current session state to re-run discovery.”

**Explicit overrides always take precedence.**

## 5.1 Profile Rulebooks & Templates Addons (Overview)

The workflow may activate a **profile rulebook** (e.g., backend Java, frontend Angular) based on repo signals.
Profiles are loaded after Phase 2 (Repo Discovery).

Some profiles additionally mandate a **templates addon** to ensure deterministic, copy-paste generation of code and tests.

Addons are manifest-driven (`profiles/addons/*.addon.yml`) and carry an explicit class:
- `addon_class: required` -> if triggered and missing: `BLOCKED-MISSING-ADDON:<addon_key>`
- `addon_class: advisory` -> if triggered and missing: WARN + recovery steps (non-blocking)

When loaded, addons MUST be recorded under `SESSION_STATE.LoadedRulebooks.addons` (addon_key -> path).

Current frontend-related addon examples:
- `angularNxTemplates` (required) -> `rules.frontend-angular-nx-templates.md`
- `frontendCypress` (advisory) -> `rules.frontend-cypress-testing.md`
- `frontendOpenApiTsClient` (advisory) -> `rules.frontend-openapi-ts-client.md`

Key constraints:
* Templates addons MUST NOT be loaded during discovery (Phase 1–3).
* If mandated by the active profile, templates addons MUST be loaded at code-phase (Phase 4+).
* If a required addon is triggered and present, it MUST be loaded.
* Addons MAY be re-evaluated and loaded later at Phase-4 re-entry/resume when new evidence appears or rulebooks are installed (supports deterministic "nachladen").
* When a templates addon is loaded, templates are binding defaults; minimal convention-aligned adaptation is allowed and must be documented.

---

## 6. Quality Requirements (High-Level)

* Java 21, Spring Boot
* Google Java Style
* no wildcard imports
* indentation: 4 spaces
* structured logging, validation, error handling
* strict adherence to architectural layers
* Contract & Schema Evolution Gate is mandatory for DB, Kafka/event schemas, OpenAPI/external contracts, and contract/persisted enums
* Change Matrix is mandatory for cross-cutting changes and MUST be verified before final output (STOP on inconsistencies)
* Mandatory Review Matrix (MRM) is mandatory in Phase 4/5/6: TicketClass + RiskTier + required artifacts must be evidenced before `ready-for-pr`
* Explicit gates should produce machine-checkable scorecards (criteria + weights + evidence refs); failed critical criteria block approval
* test coverage ≥ 80% of changed logic
* for newly created production classes, corresponding unit test classes
  (good / bad / edge cases) are mandatory
  (see `rules.md`, Chapter 10 (Test Quality))

**Build requirement:**

```bash
mvn -B -DskipITs=false clean verify
```

---

## 7. Output Requirements

Typical outputs (summary; authoritative details in master.md / rules.md):

1. **Plan** (numbered, executable)
2. **Ticket Record (Mini-ADR + NFR checklist)** (5–10 lines + NFR statuses)
3. **Diffs** (max 300 lines per block, max 5 files per response)
4. **New files** (complete)
5. **Unit / slice / integration tests**
6. **How-to-run / test instructions**
7. **Traceability matrix**
8. **Evidence list**
9. **Open issues & assumptions**

For larger changes, additionally:

* changes.patch

---

## 8. Scope Lock & No Fabrication

* Do not invent classes, files, endpoints, or fields
* If something is not present in the provided material → state so explicitly
* General knowledge may be used for explanation only, never for project-specific fabrication

---

## 9. Discovery (Phase A)

The AI extracts only:

* file and folder structures
* relevant packages and classes
* test overviews
* API endpoints and DTOs
* configurations and Flyway scripts

**No interpretation, no design, no implementation.**

---

## 10. Session State

Starting with **Phase A**, the assistant maintains a persistent canonical
**`[SESSION_STATE]`** as defined in the **Master Prompt**.

This README additionally provides a **shortened, non-normative reading view**.

### 10.1 Canonical Session State (Excerpt, partial; authoritative source: master.md)

Note: This block is a partial readability excerpt only. If it diverges from master.md, master.md is authoritative.

```text
[SESSION_STATE]
Phase=<1|1.1-Bootstrap|1.2-ProfileDetection|1.3-CoreRulesActivation|2|2.1-DecisionPack|1.5-BusinessRules|3A|3B-1|3B-2|4|5|5.3|5.4|5.5|5.6|6> | Confidence=<0-100>% | Degraded=<active|inactive>

Facts:
- ...

Decisions:
- ...

Assumptions:
- ...

Risks:
- ...

BusinessRules:
  Inventory: <count> rules | not-extracted
  Coverage:
    InPlan:  <X>/<Total> (<percent>%)
    InCode:  <X>/<Total> (<percent>%)
    InTests: <X>/<Total> (<percent>%)
  Gaps:
  - BR-ID: description
  - ...
  NewRules:
  - description
  - ...     # or: none

Gates:
  P5-Architecture: <pending|approved|rejected>
  P5.3-TestQuality: <pending|pass|pass-with-exceptions|fail>
  P5.4-BusinessRules: <pending|not-applicable|compliant|gap-detected|compliant-with-exceptions>
  P5.5-TechnicalDebt: <pending|approved|rejected|not-applicable>
  P5.6-RollbackSafety: <pending|approved|rejected|not-applicable>
  P6-ImplementationQA: <pending|ready-for-pr|fix-required>

TestQuality:        # only if Phase 5.3 is active / executed
  CoverageMatrix: <X>/<Y> methods complete (<percent>%)
  PatternViolations:
  - missing-rollback-test@PersonService.delete
  - ...
  AntiPatterns:
  - assertNotNull-only@PersonServiceTest:L42
  - ...      # or: none

Next:
- <specific next action>
[/SESSION_STATE]
```

### 10.2 README View (Collapsed, Non-Normative)

```text
[SESSION_STATE – SUMMARY]
Context:
- Repository / Module:
- Ticket / Goal:

Current Phase:
- Phase: <A|B|C|D>
- Gate Status: <OPEN|PASSED|BLOCKED>

Key Decisions:
- …

Open Questions / Blockers:
- …

Next Step:
- …
```

**Rules:**

* `master.md` / `SESSION_STATE_SCHEMA.md` are authoritative for canonical session-state semantics
* The summary view is for readability only
* Only content from provided artifacts may be recorded
* Assumptions must be explicitly labeled
* The block is updated with every response

---

## 11. Failure Cases

If artifacts are missing or corrupted:

* The AI explicitly lists the missing files
* The AI provides **only a plan**, not an implementation
* No structures, classes, or contents may be fabricated

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

**End of file — README-RULES.md**
