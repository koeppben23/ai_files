# README-RULES.md

**Executive Summary for AI-Assisted Development**

This document is the **compact overview** of all binding rules.
The full technical requirements are defined in **rules.md**.
Operational AI behavior (phases, hybrid mode, priorities, session state) is defined in the **Master Prompt**.

This document contains **no standalone rules**.
It only summarizes the requirements defined in **rules.md**.
When in doubt, **rules.md** and the **Master Prompt** always take precedence.

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
| Phase A – Analysis        | Phase 1 + 2                        |
| Phase B – Solution Design | Phase 3A + Phase 3B-1              |
| Phase C – Validation      | Phase 3B-2 + Phase 4               |
| Phase D – Implementation  | Phase 5 (+ optional 5.5) + Phase 6 |

**Extended (with Business Rules Discovery):**

| Collapsed Phase           | Master Prompt Equivalent                                 |
| ------------------------- | -------------------------------------------------------- |
| Phase A – Analysis        | Phase 1 + *1.5 (optional)* + Phase 2                     |
| Phase B – Solution Design | Phase 3A + Phase 3B-1                                    |
| Phase C – Validation      | Phase 3B-2 + Phase 4                                     |
| Phase D – Implementation  | Phase 5 + *5.4 (if 1.5 was active)* + 5.5 (optional) + 6 |

**Important:**
All **gates, sub-phases (e.g., 3B-1 / 3B-2), and constraints** apply in full,
even if not listed individually in this collapsed view.

**Business Rules Discovery (Phase 1.5):**

* Automatically enabled when >30 classes + domain layer present
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

---

## 6. Quality Requirements (High-Level)

* Java 21, Spring Boot
* Google Java Style
* no wildcard imports
* indentation: 4 spaces
* structured logging, validation, error handling
* strict adherence to architectural layers
* test coverage ≥ 80% of changed logic
* for newly created production classes, corresponding unit test classes
  (good / bad / edge cases) are mandatory
  (see rules.md, Chapter 7.3 (Test Quality Rules),
  especially 7.3.2 (Coverage Matrix per public method))

**Build requirement:**

```bash
mvn -B -DskipITs=false clean verify
```

---

## 7. Output Requirements

Each ticket produces:

1. **Plan** (numbered, executable)
2. **Diffs** (max 300 lines per block, max 5 files per response)
3. **New files** (complete)
4. **Unit / slice / integration tests**
5. **How-to-run / test instructions**
6. **Traceability matrix**
7. **Evidence list**
8. **Open issues & assumptions**

For larger changes, additionally:

* changes.patch
* README-CHANGES.md

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

### 10.1 Canonical Session State (Verbatim excerpt; authoritative source: master.md)
 
Note: This block is a readability excerpt only. If it diverges from master.md, master.md is authoritative.

```text
[SESSION_STATE]
Phase=<1|2|3A|3B-1|3B-2|4|5|5.5|6> | Confidence=<0-100>% | Degraded=<active|inactive>

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
  P5:   <pending|architecture-approved|revision-required>
  P5.3: <test-quality-pass|test-revision-required>
  P5.4: <not-applicable|business-rules-compliant|business-rules-gap-detected|compliant-with-exceptions>
  P5.5: <not-requested|approved|rejected>
  P6:   <ready-for-pr|fix-required>

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

* The canonical session state is **always authoritative**
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


