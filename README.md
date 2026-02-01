# Governance & Prompt System – Overview

This repository documents a **multi-layer governance and prompt system** for
AI-assisted software development, designed for **Lead/Staff-level quality**,
traceability, and review robustness.

The system is built to work efficiently and token-aware in both:
- **pure chat mode**, and
- **repo-aware mode with OpenCode**

This README is **descriptive**, not normative.
**If anything in this README conflicts with `master.md` or `rules.md`, treat the README as wrong and follow the rulebooks.**
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

## Repository Structure & File Placement

This system is designed for **single-user, global installation**.
All authoritative governance files are installed **once**, globally,
and reused across repositories.

Working repositories contain **no versioned governance files by default**.

The README is descriptive.
If anything here conflicts with `master.md` or `rules.md`,
the rulebooks take precedence.

---

### Global Install Layout (Authoritative)

The complete governance system is installed in:

```
~/.config/opencode/commands/
├── master.md
├── rules.md
├── QUALITY_INDEX.md
├── CONFLICT_RESOLUTION.md
├── SCOPE-AND-CONTEXT.md
├── SESSION_STATE_SCHEMA.md
├── continue.md
├── resume.md
├── ResumePrompt.md
├── ADR.md
├── TICKET_RECORD_TEMPLATE.md
├── README.md
├── README-RULES.md
├── README-OPENCODE.md
├── README-CHAT.md
└── profiles/
    ├── rules.backend-java.md
    └── rules.fallback-minimum.md
    ├── rules.frontend-angular-nx.md
    └── rules.<stack>.md
```

If any of these files are missing,
the system is considered **incomplete**
and must block or ask for correction.

---

### Optional but Recommended Files

`master.md` is the single authoritative entry point and performs
all rulebook discovery and loading.

```
repo-root/
├── README.md
├── ADR.md
├── TICKET_RECORD_TEMPLATE.md
├── README-RULES.md
├── ResumePrompt.md
```

---

### OpenCode Commands vs Repository Files

This system distinguishes clearly between:

- **Repository files** (governance, rules, context)
- **OpenCode commands** (entry points only)

All governance lives in the global OpenCode command directory.
Repositories provide **only application code and artifacts**.

---

### OpenCode Desktop: Repo-Aware Without Accidental Commits

When using **OpenCode Desktop**, the workspace is set to the repository.
For full repo-aware governance, files must therefore be **visible inside the repo tree**.

At the same time, it is often undesirable to accidentally commit
governance or prompt files into a foreign or shared repository.

The recommended setup balances both concerns.

#### Recommended Pattern

Place all governance and prompt files in a dedicated,
repo-local directory:

```
repo-root/
└── .opencode-governance/
    ├── master.md
    ├── rules.md
    ├── SCOPE-AND-CONTEXT.md
    ├── SESSION_STATE_SCHEMA.md
    ├── continue.md
    └── resume.md
```

This directory is visible to OpenCode Desktop,
but should not be committed.

#### Local Git Exclusion (No Repository Changes)

To prevent accidental commits without modifying the repository,
add the following entry to:

```
repo-root/.git/info/exclude
```

```
.opencode-governance/
```

This exclusion:
- applies only to the local clone
- does not affect other developers
- does not modify `.gitignore`

#### Canonical Entry Point

If OpenCode expects `master.md` at the repository root,
a minimal stub may exist there which delegates to:

```
.opencode-governance/master.md
```

This preserves repo discovery while keeping the full system isolated.

> Governance must be repo-visible for OpenCode,
> but not necessarily repo-versioned.

---

> Governance is global and deterministic.
> Repositories contain no prompt logic.

---

## 3. Usage in Chat (ChatGPT, Claude, etc.)

### Recommended workflow

1. **Initial context:**
   - global `master.md`
   - global `SCOPE-AND-CONTEXT.md`

2. **Working a ticket:**
   - phases proceed implicitly
   - `rules.md` is loaded automatically when required by gates

3. **Important:**
   - in chat mode, business logic can only be derived from
     provided artifacts and explicit descriptions
   - external domain truth cannot be inferred automatically

---

## 4. Usage with OpenCode (Repo-Aware)

### Recommended workflow

1. **Initial:**
   - point OpenCode Desktop to the repository (repo scan)
   - run `/master`

2. **Governance:**
   - loaded from global installation
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
- loads bootstrap governance (workflow + quality + conflict model) and defers profile/core rules
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
| `profiles/*` | Context-specific rulebooks; includes repo-agnostic fallback baseline |
| `README-RULES.md` | Executive summary (not normative) |
| `SCOPE-AND-CONTEXT.md` | Normative responsibility and scope boundary |
| `QUALITY_INDEX.md` | Canonical index for “top-tier” quality (no new rules; pointers only) |
| `CONFLICT_RESOLUTION.md` | Deterministic precedence model for conflicting instructions |
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

Copyright © 2026 Benjamin Fuchs.
Unauthorized use, copying, modification, or distribution is prohibited without explicit permission.

Note: The restrictions above do not apply to the copyright holder (Benjamin Fuchs),
who may use this Work without limitation.

_End of file_
