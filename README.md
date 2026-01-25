# Governance & Prompt System – Overview

This repository contains a **multi-layer governance and prompt system** for
AI-assisted software development, designed for **Lead/Staff-level quality**,
traceability, and review robustness.

The system is built to work efficiently and token-aware in both:
- **pure chat mode**, and
- **repo-aware mode with OpenCode**

This README is **descriptive**, not normative.
It explains purpose, structure, and usage — it does **not** control the AI’s behavior.

---

## 1. Purpose

This system addresses a central problem of modern AI-assisted development:

> How do you achieve reproducibly **high business-logic and test quality**
> without implicit assumptions, shortcuts, or hallucinations?

The answer is a **clear separation of responsibilities**, a
**phase-based workflow**, and **hard gates** for architecture,
business logic, and tests.

---

## 2. Logical Layering (Token-Optimized)

The system is intentionally organized into **three logical layers**.
These layers are **not additional rules**, but a **usage and activation recommendation**
to optimize token consumption and cognitive load.

### Layer 1 – Core Governance (Always-On)

**Purpose:**
Ensures the AI behaves correctly — regardless of context.

**Characteristics:**
- small
- always active
- determines *whether* work proceeds, not *how* it is performed

**Layer 1 includes:**
- priority ordering
- scope lock / repo-first behavior
- phase overview (1–6)
- gate rules (when code is allowed)
- session-state mechanism
- confidence / degraded / blocked behavior

**Primary files:**
- `master.md`
- `SCOPE-AND-CONTEXT.md`

This layer should **always be loaded** — both in chat and with OpenCode.

---

### Layer 2 – Quality & Logic Enforcement (Phase-Scoped)

**Purpose:**
Enforces **Lead-level quality** for architecture, business logic, and tests.

**Characteristics:**
- content-heavy
- only active when the corresponding phases are reached
- the strongest quality lever

**Layer 2 includes:**
- Business Rules Discovery (Phase 1.5)
- test quality rules (coverage matrix, anti-pattern detection)
- business-rules compliance (Phase 5.4)
- architecture and coding guidelines

**Primary file:**
- `rules.md`

This layer is **activated phase-dependently**
(e.g., 1.5, 5.3, 5.4) and does **not** need to be permanently in context.

---

### Layer 3 – Reference & Examples (Lazy-Loaded)

**Purpose:**
Serves as a **reference** and ensures correct interpretation where needed.

**Characteristics:**
- extensive
- many examples
- not decision-critical

**Source:**
- example and reference sections inside `rules.md`

This layer should be consulted **only when needed**
(ambiguity, review, audit).

---

## 3. Usage in Chat (ChatGPT, Claude, etc.)

### Recommended workflow

1. **Initial context:**
   - `master.md`
   - `SCOPE-AND-CONTEXT.md`

2. **Working a ticket:**
   - phases proceed implicitly
   - `rules.md` is added only when relevant gates require it

3. **Important:**
   - in chat mode, business logic can only be derived from
     provided artifacts and explicit descriptions
   - external domain truth cannot be inferred automatically

---

## 4. Usage with OpenCode (Repo-Aware)

### Recommended workflow

1. **Initial:**
   - point OpenCode to the repository (repo scan)
   - run `/master`

2. **Governance:**
   - `master.md`
   - `rules.md`
   - `SCOPE-AND-CONTEXT.md`
   stay permanently active

3. **Benefits:**
   - precise business-rules discovery from real code
   - tests and architecture align with repo conventions
   - fewer wrong assumptions, less review friction

OpenCode is a **quality amplifier**, not a quality guarantee.
Quality emerges from combining repo context **and** the gates in this system.

---

## 5. Commands & Session Control (OpenCode)

This repository defines three core commands:

### `/master`
Starts a new task.
- loads full governance
- initializes the workflow
- sets a new `[SESSION_STATE]`

### `/resume`
Continues an existing session **deterministically**.
- expects the last `[SESSION_STATE]`
- no re-discovery
- no reinterpretation
- no new assumptions

### `/continue`
Uniform consent to proceed.
- performs **only** the step defined in `SESSION_STATE.Next`
- does not bypass gates
- does not start new phases

---

## 6. Role of Each File

| File | Purpose |
|------|---------|
| `master.md` | Central orchestration: phases, gates, session-state |
| `rules.md` | Technical, architectural, test, and business rules |
| `README-RULES.md` | Executive summary (not normative) |
| `SCOPE-AND-CONTEXT.md` | Normative responsibility and scope boundary |
| `resume.md` | OpenCode command for controlled continuation |
| `continue.md` | OpenCode command for uniform “continue” execution |
| `ResumePrompt.md` | Manual/fallback resume variant without commands |

---

## 7. Who Is This System For?

**Suitable for:**
- Senior / Lead / Staff engineers
- review-intensive codebases
- regulated or audit-critical environments
- teams with explicit architecture and quality standards

**Not suitable for:**
- prototyping
- exploratory domain modeling
- fast MVPs without artifacts

---

## 8. Guiding Principle

> Better to block than to guess.
> Better explicit than implicit.
> Better governance than speed.

This system is intentionally conservative —
and that is precisely why it scales and remains review-robust.

---

Copyright © 2026 Benjamin Fuchs. All rights reserved.
Unauthorized use, copying, modification, or distribution is prohibited without explicit permission.

Note: The restrictions above do not apply to the copyright holder (Benjamin Fuchs),
who may use this Work without limitation.

_End of file_
