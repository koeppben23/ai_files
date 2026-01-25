# Scope & Context

This document explicitly defines what this AI-assisted development and review system is designed for —
and what it is **not** designed for. The goal is to avoid false assumptions, calibrate expectations,
and make governance decisions transparent.

This document is **normative**: deviations must be deliberate, explicit, and traceable
(e.g., via Degraded Mode, explicit overrides, or separate tickets).

---

## 1. Intended Use (IN SCOPE)

This system is **designed and optimized** for the following contexts:

### 1.1 Technology Scope

* ✅ Enterprise Java
* ✅ Spring Boot
* ✅ Maven-based builds
* ✅ Contract-first API development (OpenAPI)
* ✅ Classic backend systems (REST / optionally GraphQL)

### 1.2 Organizational & Process Scope

* ✅ Structured ticket-based development (e.g., Jira)
* ✅ Review-intensive codebases
* ✅ Multi-stage approval processes (gates)
* ✅ Regulated / audit-critical environments
* ✅ Teams with explicit architecture and quality standards

### 1.3 Primary System Goals

This system does **not** optimize for speed or creativity.
It optimizes for:

* traceability
* determinism
* review robustness
* contract fidelity
* reproducibility
* reduction of mechanical errors

---

## 2. Anti-Patterns (EXPLICITLY OUT OF SCOPE)

This system is **not** designed for the following scenarios and will intentionally
not deliver optimal results there:

### 2.1 Development Styles

* ❌ Prototyping / MVP development
* ❌ Exploratory domain modeling
* ❌ “Figure it out as we go” tickets
* ❌ Creative / experimental coding exercises
* ❌ Rapid iteration without clear artifacts

### 2.2 Technology Scope

* ❌ Non-Java stacks
* ❌ Frontend-heavy applications
* ❌ Script- or notebook-based development
* ❌ Unstructured monorepos without clear ownership

### 2.3 Expectation Anti-Patterns

* ❌ “The AI automatically understands the business domain”
* ❌ “The AI performs performance optimization”
* ❌ “The AI fully detects security vulnerabilities”
* ❌ “The AI replaces human architecture or security reviews”

---

## 3. Responsibility Boundaries

This system is **not** an autonomous developer.
It is a highly structured **engineering assistant with a governance focus**.

### 3.1 In Scope (System Responsibility)

The system takes responsibility for:

* architecture compliance (based on repository reality)
* code style and formatting
* contract adherence (OpenAPI ↔ code)
* testing obligations and coverage targets
* traceability (ticket ↔ code ↔ tests)
* evidence-based statements (scope lock)
* gate-based approvals (plan → review → QA)

### 3.2 Out of Scope (Human Responsibility)

The following areas **must** be explicitly owned by humans:

* business and semantic correctness
* security vulnerability analysis (OWASP, AuthZ, threat modeling)
* performance optimization and load testing
* algorithm selection and complexity optimization
* domain-specific decisions

The system may provide **hints or heuristics** here,
but provides **no warranty or responsibility**.

### 3.3 Partial Responsibility (Heuristics, No Guarantees)

The system provides **best-effort signals** for:

**Security:**

* ⚠️ obvious patterns (SQL injection risks, plaintext passwords)
* ⚠️ missing annotations (e.g., @PreAuthorize on sensitive endpoints)
* ❌ NO full OWASP analysis
* ❌ NO threat-modeling guarantee

**Performance:**

* ⚠️ structural risks (N+1 queries, missing indexes, nested loops)
* ⚠️ transactional boundaries (@Transactional missing/incorrect)
* ❌ NO load-test validation
* ❌ NO memory or latency optimization

**Status:** HEURISTIC — requires human validation

---

## 4. Consequences for Usage & Reviews

### 4.1 Expectation Clarity

If the system is used in a context that is **outside this scope**, the following applies:

* results must be treated as **best-effort**
* Degraded / Draft / Blocked modes are more likely
* review effort is intentionally shifted to humans

### 4.2 No Implicit Scope Shift

A scope shift (e.g., towards prototyping or exploration)

* ❌ must **not** happen implicitly
* ✅ must be made explicit (overrides, audit trail, or separate tickets)

---

## 5. Design Philosophy (Summary)

Guiding principles of this system:

* better to block than to guess
* better explicit assumptions than implicit errors
* better governance than speed
* better review robustness than creativity

This system is intentionally conservative.
This is not a weakness, but a **design decision**.

---

## 6. Target Outcome

If this system is used correctly:

* reviewers validate business correctness instead of formalities
* architecture and contract errors are eliminated early
* discussions shift from “format” to “substance”
* code reviews become shorter, more focused, and reproducible

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

# End of file — SCOPE-AND-CONTEXT.md
