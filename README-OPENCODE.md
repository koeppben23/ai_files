# OpenCode Governance & Prompt System — Usage Guide

This repository contains a **multi-layer governance and prompt system**
for **AI-assisted software development** with **Lead / Staff-level quality**,
designed for **determinism, traceability, and review robustness**.

The system is optimized to work reliably in two environments:

- **Pure chat mode** (ChatGPT, Claude, etc.)
- **Repo-aware mode using OpenCode**

---

## IMPORTANT — Read This First

This document is **descriptive, not normative**.

If anything in this README conflicts with:
- `master.md`
- `rules.md`

then **this README is wrong**.

👉 **Always follow `master.md` and `rules.md`.**

This file explains **how to use the system**,  
not **how the AI must behave**.

---

## 1. Purpose

Modern AI-assisted development often fails at:

- hidden assumptions
- hallucinated business logic
- incomplete test coverage
- architecture drift
- low review confidence

This system addresses those issues by enforcing:

- explicit scope boundaries
- a phase-based workflow
- hard quality and logic gates
- deterministic continuation via session state

The goal is **not speed**, but **reviewable, production-grade output**.

> Better to block than to guess.  
> Better explicit than implicit.  
> Better governance than speed.

---

## 2. Conceptual Layering (Token-Optimized)

The system is intentionally structured into **three conceptual layers**.

These layers are **not additional rules** and **not separate files**.
They are a **usage recommendation** to minimize token usage
and cognitive overhead.

---

### Layer 1 — Core Governance (Always On)

**Purpose:**  
Controls *whether* work may proceed.

**Characteristics:**
- small
- always active
- decision-oriented

**Includes:**
- priority order
- scope lock / repo-first behavior
- phase overview (Phases 1–6)
- gate rules (when code is allowed)
- session-state mechanism
- confidence / degraded / blocked behavior

**Primary files:**
- `master.md`
- `SCOPE-AND-CONTEXT.md`

This layer **must always be active**, in chat and in OpenCode.

---

### Layer 2 — Quality & Logic Enforcement (Phase-Scoped)

**Purpose:**  
Enforces **Lead-level quality** for architecture,
business logic, and tests.

**Characteristics:**
- content-heavy
- activated only when relevant phases are reached
- strongest quality lever

**Includes:**
- Business Rules Discovery (Phase 1.5)
- Change Matrix
- Contract & Schema Evolution Gate
- test quality rules and anti-pattern detection
- business rules compliance (Phase 5.4)

**Primary file:**
- `rules.md`

This layer is **loaded only when required by the workflow**.
It does **not** need to be permanently in context.

---

### Layer 3 — Reference & Examples (Lazy-Loaded)

**Purpose:**  
Clarifies interpretation and supports audits and reviews.

**Characteristics:**
- extensive
- example-heavy
- not decision-critical

**Source:**
- example and reference sections inside `rules.md`

This layer should be consulted **only when needed**.

---

## 3. Using the System in Chat (No OpenCode)

Recommended approach:

1. Provide:
   - `master.md`
   - `SCOPE-AND-CONTEXT.md`

2. Work through a ticket:
   - phases advance implicitly
   - gates block automatically when required

3. Important limitations:
   - business logic can only be derived from
     provided artifacts or explicit descriptions
   - no repository → no implicit domain truth

Chat mode is suitable for:
- planning
- reviews
- architecture discussions
- non-repo-bound analysis

---

## 4. Using the System with OpenCode (Repo-Aware)

OpenCode enables **repo-first governance**.

### Recommended workflow

1. **Initialization**
   - Point OpenCode to the repository
   - Let it index the repo
   - Run `/master`

2. **Active governance**
   - `master.md`
   - `rules.md`
   - `SCOPE-AND-CONTEXT.md`

   remain available during the session

3. **Benefits**
   - real business-rule discovery from actual code
   - architecture aligned with repository conventions
   - accurate test scaffolding
   - fewer wrong assumptions
   - lower review friction

4. **Optional: ADR decision memory**
   - If you keep an `ADR.md` in the repo, the system can reuse past architecture decisions
   - This reduces repeated discussions and prevents silent architecture drift

> OpenCode is a **quality amplifier**, not a quality guarantee.  
> Quality emerges from **repo context + enforced gates**.

---

## 5. OpenCode Commands & Session Control

This repository defines three core OpenCode commands.

These commands are **OpenCode-specific**  
and do **not** apply to pure chat environments.

---

### `/master`

Starts a new task.

- loads full governance
- initializes the workflow
- creates a fresh `[SESSION_STATE]`

Use this for:
- new tickets
- new scopes
- fresh analysis

---

### `/resume`

Continues an existing session **deterministically**.

- expects the last `[SESSION_STATE]`
- no rediscovery
- no reinterpretation
- no new assumptions

Use this when:
- a session was interrupted
- you want guaranteed continuity

---

### `/continue`

Uniform consent to proceed.

- executes **only** what is defined in `SESSION_STATE.Next`
- does not bypass gates
- does not start new phases

Use this to:
- advance safely
- confirm the next step without ambiguity

---

## 6. File Responsibilities (Quick Reference)

| File | Purpose |
|-----|--------|
| `master.md` | Workflow orchestration, phases, gates, session state |
| `rules.md` | Technical, architectural, test, and business rules |
| `README-RULES.md` | Executive summary (not normative) |
| `SCOPE-AND-CONTEXT.md` | Normative scope and responsibility boundaries |
| `resume.md` | OpenCode command for controlled continuation |
| `continue.md` | OpenCode command for uniform continuation |
| `ResumePrompt.md` | Manual fallback resume variant |

---

## 7. Intended Audience

**Well-suited for:**
- Senior / Lead / Staff engineers
- review-intensive codebases
- regulated or audit-sensitive environments
- teams with explicit quality standards

**Not intended for:**
- rapid prototyping
- exploratory domain modeling
- MVPs without real artifacts

---

## 8. Guiding Principles

- Better to block than to guess
- Better explicit than implicit
- Better governance than speed

This system is intentionally conservative —
that is why it scales and remains review-robust.

---

Copyright © 2026 Benjamin Fuchs.  
All rights reserved.

Unauthorized use, copying, modification, or distribution
is prohibited without explicit permission.

Note: These restrictions do not apply to the copyright holder
(Benjamin Fuchs), who may use this work without limitation.

_End of file_
