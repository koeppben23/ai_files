# Governance & Prompt System – Overview

## 📌 README Index

This document is part of a multi-layer AI governance system.  
Use the following guide to navigate responsibilities and authority:

- **Looking for mandatory rules and system behavior?**  
  → See `master.md` (normative, highest priority)

- **Looking for technical and quality constraints?**  
  → See `rules.md`

- **Looking for stack- or context-specific rules?**  
  → See `profiles/*`

- **Looking for OpenCode configuration and persistence details?**  
  → See `README-OPENCODE.md`

- **Looking for how to start or resume a session?**  
  → See `start.md`, `continue.md`, `resume.md`

This README is **descriptive only** and must not be interpreted as normative.

This repository documents a **multi-layer governance and prompt system** for AI-assisted software development, designed for **Lead/Staff-level quality**, traceability, and review robustness.

The system is built to work efficiently and token-aware in both:

- **pure chat mode**, and
- **repo-aware mode with OpenCode**

This README is **descriptive**, not normative.  
**If anything in this README conflicts with `master.md` or `rules.md`, treat the README as wrong and follow the rulebooks.**  
It explains purpose, structure, and usage — it does **not** control the AI’s behavior.

---

## Quick Start Matrix (Operational)

Choose the workflow entry based on what you are doing:

- **New repo / first time:** run `/master` and let Phase 1–2 build discovery artifacts; do not skip Phase 2.
- **New ticket on a known repo:** run `/master` (Warm Start). The system will reuse cache/digest/memory if valid.
- **Resume an interrupted ticket/session:** follow `continue.md` / `resume.md` using the active session pointer (`${SESSION_STATE_POINTER_FILE}`) and repo session file (`${SESSION_STATE_FILE}`).
- **Audit a completed change:** run `/master` and jump to the relevant explicit gates (Contract Gate, Test Quality Gate, Phase 6 QA).

---

## Installation & Paths (Descriptive; Source of truth is `master.md`)

`master.md` defines canonical path variables and derived paths. At a high level:

- `${CONFIG_ROOT}` is resolved by the runtime (see `master.md`).
- On Windows/macOS/Linux, `${CONFIG_ROOT}` is resolved per `master.md` (do not hard-code OS paths).
- `${COMMANDS_HOME} = ${CONFIG_ROOT}/commands`
- `${PROFILES_HOME} = ${COMMANDS_HOME}/profiles`
- `${WORKSPACES_HOME} = ${CONFIG_ROOT}/workspaces`

**Where files live:**

- Global rulebooks (`master.md`, `rules.md`) are installed under `${COMMANDS_HOME}`.
- Profile rulebooks are installed under `${PROFILES_HOME}`.
- Repo-specific persistent artifacts live under `${WORKSPACES_HOME}/<repo_fingerprint>/...` (cache, digest, decision pack, business rules, workspace memory).
- Session payload is repo-scoped: `${SESSION_STATE_FILE}` under `${WORKSPACES_HOME}/<repo_fingerprint>/...`.
- Global `${SESSION_STATE_POINTER_FILE}` is the active-session pointer used to select the repo-scoped session state.
- `${RESUME_FILE}` remains global unless a repo-scoped resume strategy is explicitly enabled.

If your environment uses different locations, follow `master.md` and update the variable resolution, not the docs.

---

## Installer (Optional, recommended for deterministic setups)

This repo ships an `install.py` (LLM Governance System Installer) that installs the governance files to the **OpenCode config root** and creates the expected directory layout. It is intended to avoid interactive path binding and reduce “works on my machine” drift.

### Target paths (descriptive)

- **Windows (primary):** `%USERPROFILE%\.config\opencode`  
- **Windows (fallback):** `%APPDATA%\opencode` (only if `USERPROFILE` is unavailable)
- **Linux/macOS:** `${XDG_CONFIG_HOME:-~/.config}/opencode`

Installed layout:

- `${CONFIG_ROOT}/commands/` (rulebooks + commands)
- `${CONFIG_ROOT}/commands/profiles/` (profile rulebooks)
- `${CONFIG_ROOT}/workspaces/` (repo-scoped persistence: cache/digest/memory/etc.)

### What gets installed

- `commands/` (examples):
  - `master.md`, `rules.md`, `start.md`, `continue.md`, `resume.md`
  - `new_profile.md`, `new_addon.md` (factory commands for principal-grade profile/addon creation)
  - `SESSION_STATE_SCHEMA.md`, `QUALITY_INDEX.md`, `CONFLICT_RESOLUTION.md`
  - `SCOPE-AND-CONTEXT.md`, `TICKET_RECORD_TEMPLATE.md`, `ADR.md`, `resume_prompt.md`, …
- `commands/profiles/`:
  - `profiles/*.md` (all profile rulebooks)
  - `profiles/addons/*.addon.yml` (addon manifests for required/advisory activation)
- `commands/diagnostics/`:
  - `diagnostics/**` (audit tooling, schemas, documentation, factory contracts such as `PROFILE_ADDON_FACTORY_CONTRACT.json`, and recovery helpers such as `bootstrap_session_state.py`)

### Safety & operational behavior

- **Fail-closed precheck:** Install fails if critical files are missing (`master.md`, `rules.md`, `start.md`).
- **Backup on overwrite:** With `--force`, the installer writes a timestamped backup under `commands/_backup/<timestamp>/...` before overwriting (disable via `--no-backup`).
- **Manifest-based uninstall:** Uninstall removes **only** what the installer recorded in the manifest (does not blindly delete `commands/`).
- **Governance paths bootstrap:** By default, the installer creates `${COMMANDS_HOME}/governance.paths.json` and fills in the resolved paths (`configRoot`, `commandsHome`, `profilesHome`, `workspacesHome`). This file is **installer-owned** and is used by `/start` to auto-bind canonical paths without interactive input.
  - It **will not overwrite** an existing `governance.paths.json` unless you use `--force`.
  - To disable this step entirely: use `--skip-paths-file`.

### Usage

Show help / options:

```bash
python install.py --help
```

Dry-run (recommended):

```bash
python install.py --dry-run
```

Install (interactive):

```bash
python install.py
```

Install (non-interactive overwrite, with backup):

```bash
python install.py --force
```

Install (overwrite, no backup):

```bash
python install.py --force --no-backup
```

Custom source directory (if files are not next to `install.py`):

```bash
python install.py --source-dir /path/to/governance-files
```

Skip writing `governance.paths.json` (if you manage it manually):

```bash
python install.py --skip-paths-file
```

Override config root (useful for CI/tests):

```bash
python install.py --config-root /tmp/opencode-test --dry-run
python install.py --config-root /tmp/opencode-test --force
```

### Uninstall (manifest-based)

Uninstall (interactive):

```bash
python install.py --uninstall
```

**Note:**
`governance.paths.json` is machine-specific.
It is removed on uninstall only if it was created or overwritten by the installer
(i.e. if it is listed in the install manifest).

If the file pre-existed and was skipped, the installer does not take ownership
and it will be preserved.

To remove a preserved file, delete `${COMMANDS_HOME}/governance.paths.json` manually (or run `python install.py --uninstall --force --purge-paths-file`).

Uninstall (non-interactive):

```bash
python install.py --uninstall --force
```

Uninstall dry-run:

```bash
python install.py --uninstall --dry-run
```

### Manifest & version tracking

The installer writes a manifest file:

- `${CONFIG_ROOT}/commands/INSTALL_MANIFEST.json`

Typical content (high level):

- `installerVersion`
- `governanceVersion` (required; extracted from `master.md`, e.g. `# Governance-Version: <semver>`)
- installed file list + checksums + backup metadata

### Recommended test matrix before release

**Windows 10/11**

- primary: `%USERPROFILE%\.config\opencode`
- fallback: `%APPDATA%\opencode`

**macOS**

- `~/.config/opencode` or `$XDG_CONFIG_HOME/opencode`

**Linux**

- `~/.config/opencode` or `$XDG_CONFIG_HOME/opencode`

Suggested test sequence:

```bash
python install.py --dry-run
python install.py
python install.py --force
python install.py --force --no-backup
python install.py --uninstall --dry-run
python install.py --uninstall
```

---

## OpenCode Local Configuration (Required for Repo-Aware Mode)

When using this governance system with **OpenCode (repo-aware execution)**, a **local machine configuration file is REQUIRED** to avoid interactive path binding and non-deterministic startup behavior.

This repository does not ship a machine-specific OpenCode configuration file. Each machine must provide its own `${COMMANDS_HOME}/governance.paths.json`.

### Local instance (NOT checked in)

Each user must have a local configuration file at:

- **Linux / macOS**
  ```
  ~/.config/opencode/commands/governance.paths.json
  ```

- **Windows**
  ```
  %USERPROFILE%\.config\opencode\commands\governance.paths.json
  ```

This file is **machine-specific** and MUST NOT be committed.

### Setup (one-time)

If you use the provided installer (`install.py`), it will create `governance.paths.json` automatically (recommended):

```bash
python install.py
```

Manual setup (if you prefer):

1. Create the file:
   - To:   `${COMMANDS_HOME}/governance.paths.json`

2. Populate it with absolute paths on your machine.

Example (Windows):

```json
{
  "schema": "opencode-governance.paths.v1",
  "generatedAt": "2026-02-04T12:00:00",
  "paths": {
    "configRoot": "C:/Users/<USER>/.config/opencode",
    "commandsHome": "C:/Users/<USER>/.config/opencode/commands",
    "profilesHome": "C:/Users/<USER>/.config/opencode/commands/profiles",
    "diagnosticsHome": "C:/Users/<USER>/.config/opencode/commands/diagnostics",
    "workspacesHome": "C:/Users/<USER>/.config/opencode/workspaces"
  }
}
```

After this, `/start` can load the file automatically and you do **not** need to paste or type paths.

**Important:**  
Interactive path binding is intentionally avoided.  
If `/start` cannot load `governance.paths.json`, your local installation is incomplete.

---

## 1. Purpose

This system addresses a central problem of modern AI-assisted development:

> How do you achieve reproducibly **high business-logic and test quality**
> without implicit assumptions, shortcuts, or hallucinations?

The answer is a **clear separation of responsibilities**, a **phase-based workflow**, and **hard gates** for architecture, business logic, and tests.

---

## 1.1 End-to-End Phase Map (Operational)

The workflow below summarizes every active phase/sub-phase used by this system.
If this section and `master.md` ever differ, `master.md` is authoritative.

| Phase | What it does (one-line) | Gate / blocked behavior |
| ----- | ------------------------ | ----------------------- |
| Phase 0 — Bootstrap (conditional) | Validates variable/path bootstrap when required before workflow execution. | If bootstrap evidence or variable resolution is invalid/missing, workflow is `BLOCKED` (fail-closed). |
| Phase 1 — Rules Loading | Loads rulebooks lazily in controlled order (bootstrap now, profile after discovery, core/templates/addons before planning). | Blocks if required rulebooks/evidence cannot be resolved for the current phase. |
| Phase 2 — Repository Discovery | Builds repo understanding (structure, stack, architecture signals, contract surface), with cache-assisted warm start when valid. | Non-gate phase, but missing required discovery artifacts can trigger `BLOCKED` continuation pointers. |
| Phase 2.1 — Decision Pack (default, non-gate) | Distills discovery outputs into reusable decisions/defaults for later phases. | Non-gate; if evidence is insufficient, decisions remain `not-verified` and downstream confidence is capped. |
| Phase 1.5 — Business Rules Discovery (optional) | Extracts business rules from code/ticket artifacts when activated or required. | Optional activation; once executed, Phase 5.4 becomes mandatory for code readiness. |
| Phase 3A — API Inventory | Inventories external API artifacts and interface landscape. | Non-gate validation stage; blocks only when required API evidence is missing for active scope. |
| Phase 3B-1 — API Logical Validation | Validates API specs for logical consistency at specification level. | Non-gate validation stage; unresolved spec issues can block progression to later contract-sensitive steps. |
| Phase 3B-2 — Contract Validation (Spec ↔ Code) | Validates contract fidelity between specification and implementation. | Contract mismatches block readiness when contract gates are active/applicable. |
| Phase 4 — Ticket Execution (planning) | Produces the concrete implementation plan and review artifacts; no code output yet. | Planning phase; code-producing output remains blocked until explicit gate progression permits it. |
| Phase 5 — Lead Architect Review (gate) | Architecture gatekeeper review for feasibility, risk, and quality readiness. | Explicit gate; failure blocks progression to implementation readiness. |
| Phase 5.3 — Test Quality Review (critical gate) | Reviews test strategy/coverage quality against gate criteria. | Critical gate; must pass (or pass with governed exceptions) before PR readiness. |
| Phase 5.4 — Business Rules Compliance (conditional gate) | Checks implemented plan/output against extracted business rules. | Mandatory only if Phase 1.5 ran; non-compliance blocks readiness. |
| Phase 5.5 — Technical Debt Proposal (optional gate) | Reviews and decides technical debt proposals and mitigation posture. | Optional gate; when activated, unresolved debt decisions can block approval. |
| Phase 5.6 — Rollback Safety | Evaluates rollback/recovery safety for relevant changes (within Phase 5 family). | Required when rollback-sensitive changes exist; failed rollback safety blocks progression. |
| Phase 6 — Implementation QA (final gate) | Final quality assurance and release-readiness decision (`ready-for-pr` vs `fix-required`). | Final explicit gate; failed QA blocks PR readiness. |

### Phase-Coupled Persistence (Outside Repository)

| Phase | Artifact | Target | Write condition |
| ----- | -------- | ------ | --------------- |
| Phase 2 | `repo-cache.yaml` | `${REPO_CACHE_FILE}` (`[REPO-CACHE-FILE]`) | Written after successful discovery / cache refresh. |
| Phase 2 | `repo-map-digest.md` | `${REPO_DIGEST_FILE}` (`[REPO-MAP-DIGEST-FILE]`) | Written after successful discovery digest generation. |
| Phase 2 | `workspace-memory.yaml` (observations/patterns) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Allowed for observational memory writeback when discovery evidence is sufficient. |
| Phase 2.1 | `decision-pack.md` | `${REPO_DECISION_PACK_FILE}` (`[DECISION-PACK-FILE]`) | Written when at least one decision/default is produced. |
| Phase 1.5 | `business-rules.md` | `${REPO_BUSINESS_RULES_FILE}` (`[BR-INVENTORY-FILE]`) | Written when Business Rules Discovery is executed. |
| Phase 5 (conditional) | `workspace-memory.yaml` (decisions/defaults) | `${WORKSPACE_MEMORY_FILE}` (`[WORKSPACE-MEMORY-FILE]`) | Only when Phase 5 is approved **and** user confirms exactly: `Persist to workspace memory: YES`. |

---

## 2. Logical Layering (Token-Optimized)

The system is intentionally organized into **three logical layers**.  
These layers are **not additional rules**, but a **usage and activation recommendation** to optimize token consumption and cognitive load.

The exact loading behavior and activation timing are defined exclusively in `master.md`.

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

**Layer 1 files:**

- `master.md`
- `SCOPE-AND-CONTEXT.md`

This layer is **installed globally** and made available to the workflow.  
Actual loading order and timing are controlled by `master.md`.

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

This layer is **activated phase-dependently** (e.g., 1.5, 5.3, 5.4) and does **not** need to be permanently in context.

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

This layer should be consulted **only when needed** (ambiguity, review, audit).

---

## Repository Structure & File Placement

This system is designed for **single-user, global installation**.  
All authoritative governance files are installed **once**, globally, and reused across repositories.

### Persistent State & Storage Locations (Descriptive)

All persisted workflow state and derived artifacts live **outside the repository** under the OpenCode configuration root.

Canonical locations (see `master.md` for binding definitions):

- `${SESSION_STATE_POINTER_FILE}` – active session pointer (global)
- `${SESSION_STATE_FILE}` – repo-scoped canonical session state
- `${RESUME_FILE}` – deterministic resume pointer
- `${REPO_IDENTITY_MAP_FILE}` – stable repo identity mapping
- `${WORKSPACES_HOME}/<repo_fingerprint>/` – repo-scoped workspace bucket
  - `decisions/ADR.md`
  - `repo-map-digest.md`
  - `decision-pack.md`
  - `business-rules.md`
  - `workspace-memory.yaml`

Repositories themselves remain free of governance state and memory artifacts.

Working repositories contain **no versioned governance files by default**.

---

### Global Install Layout (Authoritative)

## Canonical Path Variables

The rulebooks define a single canonical configuration root and derive all other paths from it.

- `${CONFIG_ROOT}` is the OpenCode configuration root (OS-specific):
  - `${CONFIG_ROOT}` is resolved per `master.md` (do not hard-code OS paths).
  - (OS-specific resolution is described in `master.md`.)

All governance file lookups and all persisted artifacts MUST use `${CONFIG_ROOT}` or a derived path variable (e.g., `${COMMANDS_HOME}`, `${WORKSPACES_HOME}`), to avoid hard-coded paths and OS-specific duplication.

The authoritative global install layout remains under `${COMMANDS_HOME}`:  
`${CONFIG_ROOT}/commands/…`

The complete governance system is installed in:

```
${COMMANDS_HOME}/
├── master.md
├── rules.md
├── start.md
├── QUALITY_INDEX.md
├── CONFLICT_RESOLUTION.md
├── SCOPE-AND-CONTEXT.md
├── SESSION_STATE_SCHEMA.md
├── governance.paths.json
├── INSTALL_MANIFEST.json
├── continue.md
├── resume.md
├── resume_prompt.md
├── ADR.md
├── TICKET_RECORD_TEMPLATE.md
├── README.md
├── README-RULES.md
├── README-OPENCODE.md
├── README-CHAT.md
├── profiles/
│   ├── rules.backend-java.md
│   ├── rules.frontend-angular-nx.md
│   ├── rules.fallback-minimum.md
│   ├── rules.<stack>.md
│   └── addons/
│       ├── angularNxTemplates.addon.yml
│       └── <addon>.addon.yml
└── diagnostics/
    ├── AUDIT_REPORT_SCHEMA.json
    └── audit.md
```

If any of these files are missing, the workflow behavior is determined by the blocking rules defined in `master.md`.

---

### Optional but Recommended Files

`master.md` is the single authoritative entry point and performs all rulebook discovery and loading.

---

### OpenCode Commands vs Repository Files

This system distinguishes clearly between:

- **Repository files** (governance, rules, context)
- **OpenCode commands** (entry points only)

All governance lives in the global OpenCode command directory.  
Repositories provide **only application code and artifacts**.

---

### OpenCode Desktop: Repo-Aware Execution Model

OpenCode operates on a repository working directory, but **governance resolution and persistence are strictly external to the repository**.

All rulebooks, prompts, and persisted state are resolved from the global OpenCode configuration root (`${CONFIG_ROOT}`) and its derived paths, as defined in `master.md`.

Repositories MUST NOT contain authoritative governance or prompt logic.

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
   - in chat mode, business logic can only be derived from provided artifacts and explicit descriptions
   - external domain truth cannot be inferred automatically

---

## 4. Usage with OpenCode (Repo-Aware)

### Recommended workflow

1. **Initial:**
   - point OpenCode Desktop to the repository (repo scan)
   - run `/master`

2. **Governance:**
   - loaded from global installation
   - stays permanently active

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

### `/audit`

Read-only diagnostics command.  
Outputs an `AUDIT_REPORT` JSON (see schema) and may update only:  
`SESSION_STATE.Audit.LastRun.*` (pointer + hash), without touching workflow control fields.

See:

- `diagnostics/audit.md`
- `diagnostics/AUDIT_REPORT_SCHEMA.json`

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
| `resume_prompt.md` | Manual/fallback resume variant without commands |

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

This system is intentionally conservative — and that is precisely why it scales and remains review-robust.

---

Copyright © 2026 Benjamin Fuchs.  
Unauthorized use, copying, modification, or distribution is prohibited without explicit permission.

Note: The restrictions above do not apply to the copyright holder (Benjamin Fuchs), who may use this Work without limitation.

_End of file_
