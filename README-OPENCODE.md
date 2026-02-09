# OpenCode Governance & Prompt System — Usage Guide

## 📌 README Index

This document explains OpenCode-specific configuration and persistence.
It does not define system behavior.

- **Normative system rules and gates**  
  → See [`master.md`](master.md)

- **Quality and technical constraints**  
  → See [`rules.md`](rules.md)

- **Profiles and stack-specific rules**  
  → See [`profiles/`](profiles/)

- **Session lifecycle (start / continue / resume)**  
  → See [`start.md`](start.md), [`continue.md`](continue.md), [`resume.md`](resume.md)

- **Release/readiness stability contract**
  → See [`STABILITY_SLA.md`](STABILITY_SLA.md)

- **Canonical session-state schema**
  → See [`SESSION_STATE_SCHEMA.md`](SESSION_STATE_SCHEMA.md)

This README is descriptive and subordinate to all normative files.

## 🔎 Quick Navigation (This File)

- [Cold Start vs Warm Start](#cold-start-vs-warm-start-repo-aware-mode)
- [Factory Workflow](#factory-workflow-for-new-profilesaddons-operational)
- [Session State Bootstrap Recovery](#session-state-bootstrap-recovery-operational)
- [Installation Layout](#installation-layout-descriptive-follow-mastermd-if-in-doubt)
- [OpenCode Commands & Session Control](#5-opencode-commands--session-control)
- [File Responsibilities](#6-file-responsibilities-quick-reference)
- [Intended Audience](#7-intended-audience)


This repository contains a **multi-layer governance and prompt system**
for **AI-assisted software development** with **Lead / Staff-level quality**,
designed for **determinism, traceability, and review robustness**.

The system is optimized to work reliably in two environments:

- **Pure chat mode** (ChatGPT, Claude, etc.)
- **Repo-aware mode using OpenCode**

---

## IMPORTANT — Read This First

This document is **descriptive, not normative**.

## Cold Start vs Warm Start (Repo-aware mode)

The workflow behaves differently depending on whether prior repo discovery artifacts exist.

### Cold Start (first run on a repo)
Use when:
- the repo has never been analyzed in this workspace, or
- repo structure/contracts changed materially and caches must be rebuilt.

What happens:
- Phase 2 performs full repo discovery and generates/refreshes repo map/cache artifacts.
- Templates/Addons activation in Phase 4 uses discovery evidence from Phase 2.

### Warm Start (new ticket, same repo)
Use when:
- you start a new session for a new ticket on the same repo, and
- repo caches/digests are still valid (git head / repo signature matches as defined in `master.md`).

What happens:
- Phase 2 can take a fast-path using existing cache/digest/memory.
- The system still re-evaluates Templates/Addons at Phase 4 entry using the recorded evidence signals.

If Warm Start eligibility is not met, the system MUST fall back to Cold Start automatically.

---

## Factory Workflow for New Profiles/Addons (Operational)

Use this when a new repository/ticket needs governance coverage that does not exist yet.

- Create a new profile rulebook with `new_profile.md`.
- Create a new addon pair with `new_addon.md` (rulebook + manifest).
- Enforce principal-grade baseline in generated artifacts:
  - `Principal Excellence Contract (Binding)`
  - `Principal Hardening v2.1 - Standard Risk Tiering (Binding)`
  - `Principal Hardening v2.1.1 - Scorecard Calibration (Binding)`
- Validate output against [`diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json`](diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json).

Minimum operator input for generation:

- profile/addon key and target scope
- applicability signals (descriptive only; not selection logic)
- addon class (`required` or `advisory`) for addons
- quality focus and blocking policy

Recommended commit messages:

- `feat(governance): add <profile_key> principal profile rulebook`
- `feat(governance): add <addon_key> principal addon and manifest`

---

## Session State Bootstrap Recovery (Operational)

If `/audit` or continuation commands fail because `SESSION_STATE` is missing, initialize canonical repo-scoped session state and the active pointer:

```bash
python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>
```

Use the same deterministic repo fingerprint your governance flow already uses for `${REPO_HOME}`.
If needed, derive it from repo identity evidence (`remote URL | default branch`) and reuse that value consistently.

Useful options:

```bash
python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --dry-run
python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --force
python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --config-root /tmp/opencode-test
```

This creates:

- `${SESSION_STATE_FILE}` (`${WORKSPACES_HOME}/<repo_fingerprint>/SESSION_STATE.json`) with a safe `1.1-Bootstrap` blocked baseline
- `${SESSION_STATE_POINTER_FILE}` (`${OPENCODE_HOME}/SESSION_STATE.json`) as active pointer to the repo-scoped session

so governance can resume deterministically across multiple repositories.

To backfill missing repo-scoped persistence artifacts (cache/digest/decision-pack/workspace-memory):

```bash
python diagnostics/persist_workspace_artifacts.py --repo-root <repo_path>
```

Useful options:

```bash
python diagnostics/persist_workspace_artifacts.py --repo-root <repo_path> --dry-run
python diagnostics/persist_workspace_artifacts.py --repo-root <repo_path> --repo-fingerprint <repo_fingerprint>
python diagnostics/persist_workspace_artifacts.py --repo-fingerprint <repo_fingerprint> --force
python diagnostics/persist_workspace_artifacts.py --repo-fingerprint <repo_fingerprint> --no-session-update
```

Fingerprint resolution order in the helper:

1. explicit `--repo-fingerprint`
2. deterministic git metadata from `--repo-root` (or current working directory)
3. global `${SESSION_STATE_POINTER_FILE}` fallback

`/start` also invokes this helper automatically when the installer-provided command exists.

Runtime error logging:

- Repo-aware errors are appended to `${WORKSPACES_HOME}/<repo_fingerprint>/logs/errors-YYYY-MM-DD.jsonl`.
- Global fallback errors are appended to `${CONFIG_ROOT}/logs/errors-global-YYYY-MM-DD.jsonl`.
- The log shape is JSONL (`schema: opencode.error-log.v1`) for deterministic machine parsing.
- A per-directory summary index is maintained at `errors-index.json`.
- Old `errors-*.jsonl` files are pruned automatically (default retention: 30 days).
- Installer uninstall purges matching runtime error logs by default (`--keep-error-logs` to preserve them).

---

## Installation Layout (Descriptive; follow `master.md` if in doubt)

`master.md` defines canonical path variables. Typical layout:

- `${CONFIG_ROOT}`: `${XDG_CONFIG_HOME:-~/.config}/opencode`
- On Windows, `${CONFIG_ROOT}` is `%USERPROFILE%\.config\opencode` (fallback: `%APPDATA%\opencode`) — see `master.md`.
- `${COMMANDS_HOME} = ${CONFIG_ROOT}/commands` (global rulebooks)
- `${PROFILES_HOME} = ${COMMANDS_HOME}/profiles` (profiles + templates/addons)
- `${REPO_OVERRIDES_HOME} = ${WORKSPACES_HOME}/<repo_fingerprint>/governance-overrides` (optional workspace-local overrides; outside repo working tree)
- `${WORKSPACES_HOME} = ${CONFIG_ROOT}/workspaces` (per-repo caches/digests/memory artifacts)
- `${SESSION_STATE_FILE} = ${WORKSPACES_HOME}/<repo_fingerprint>/SESSION_STATE.json` (repo-scoped session payload)
- `${SESSION_STATE_POINTER_FILE} = ${OPENCODE_HOME}/SESSION_STATE.json` (global active-session pointer)
- `${RESUME_FILE}` stays global under `${CONFIG_ROOT}`/`${OPENCODE_HOME}` unless repo-scoped resume is enabled.

Profiles can mandate templates/addons (e.g., `backend-java` requires `rules.backend-java-templates.md` and may require `rules.backend-java-kafka-templates.md` based on evidence).

Resolution scope note:
- `/start` enforces installer-owned roots (`${COMMANDS_HOME}`, `${PROFILES_HOME}`) as canonical entrypoint requirements.
- Runtime may additionally resolve workspace/local overrides and global fallbacks (`${REPO_OVERRIDES_HOME}`, `${OPENCODE_HOME}`) per `master.md`, without weakening entrypoint contracts.


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

### Component Scope (Required for Monorepo Code Work)

If your repo is a monorepo or contains multiple stacks, provide a bounded scope in the ticket, e.g.:
- `ComponentScope: services/order-service, libs/shared`
or
- `Work only in: apps/web`

This is required before code-producing work in monorepos, reducing profile ambiguity and preventing unintended cross-component changes.

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
   - Run `/start` once (bootstrap/path contract + workspace persistence checks)
   - Run `/master` to begin the ticket flow

2. **Active governance**
   - `master.md`
   - `rules.md`
   - `SCOPE-AND-CONTEXT.md`
   - `QUALITY_INDEX.md`
   - `CONFLICT_RESOLUTION.md`

   remain available during the session

3. **Benefits**
   - real business-rule discovery from actual code
   - architecture aligned with repository conventions
   - accurate test scaffolding
   - fewer wrong assumptions
   - lower review friction

4. **Weak or missing repo standards**
   - If the repository lacks explicit build/test/quality standards, activate:
     - `profiles/rules.fallback-minimum.md`
   - This establishes a non-negotiable baseline for verification and documentation.

5. **Optional: ADR decision memory**
   - If you keep an `ADR.md` in the repo, the system can reuse past architecture decisions
   - This reduces repeated discussions and prevents silent architecture drift

> OpenCode is a **quality amplifier**, not a quality guarantee.  
> Quality emerges from **repo context + enforced gates**.

---

## 5. OpenCode Commands & Session Control

This command package defines core OpenCode commands.

These commands are **OpenCode-specific**  
and do **not** apply to pure chat environments.

---

### `/master`

Starts a new task.

- loads workflow + precedence + gating bootstrap
- loads `rules.md`, active profile, and addons/templates phase-scoped per `master.md` (not as optional policy)
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

### `/audit`

Read-only diagnostics command.
Outputs an `AUDIT_REPORT` JSON (see schema) and may update only:
`SESSION_STATE.Audit.LastRun.*` (pointer + hash), without touching workflow control fields.

See:
- [`diagnostics/audit.md`](diagnostics/audit.md)
- [`diagnostics/AUDIT_REPORT_SCHEMA.json`](diagnostics/AUDIT_REPORT_SCHEMA.json)

---

## 6. File Responsibilities (Quick Reference)

| File | Purpose |
|-----|--------|
| [`master.md`](master.md) | Workflow orchestration, phases, gates, session state |
| [`STABILITY_SLA.md`](STABILITY_SLA.md) | Normative governance release/readiness Go/No-Go contract |
| [`rules.md`](rules.md) | Technical, architectural, test, and business rules |
| [`README-RULES.md`](README-RULES.md) | Executive summary (not normative) |
| [`SCOPE-AND-CONTEXT.md`](SCOPE-AND-CONTEXT.md) | Normative scope and responsibility boundaries |
| [`QUALITY_INDEX.md`](QUALITY_INDEX.md) | Canonical index for “top-tier” quality (no new rules; pointers only) |
| [`SESSION_STATE_SCHEMA.md`](SESSION_STATE_SCHEMA.md) | Canonical session-state schema and invariants |
| [`CONFLICT_RESOLUTION.md`](CONFLICT_RESOLUTION.md) | Deterministic precedence model for conflicting instructions |
| [`resume.md`](resume.md) | OpenCode command for controlled continuation |
| [`continue.md`](continue.md) | OpenCode command for uniform continuation |
| [`resume_prompt.md`](resume_prompt.md) | Manual fallback resume variant |

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
