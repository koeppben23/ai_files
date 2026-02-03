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

## Quick Start Matrix (Operational)

Choose the workflow entry based on what you are doing:

- **New repo / first time:** run `/master` and let Phase 1–2 build discovery artifacts; do not skip Phase 2.
- **New ticket on a known repo:** run `/master` (Warm Start). The system will reuse cache/digest/memory if valid.
- **Resume an interrupted ticket/session:** follow `continue.md` / `resume.md` using the existing `SESSION_STATE.json`.
- **Audit a completed change:** run `/master` and jump to the relevant explicit gates (Contract Gate, Test Quality Gate, Phase 6 QA).

---

## Installation & Paths (Descriptive; Source of truth is `master.md`)

`master.md` defines canonical path variables and derived paths. At a high level:

- `${CONFIG_ROOT}` is resolved by the runtime (see `master.md`).
- On Windows/macOS/Linux, `${CONFIG_ROOT}` is resolved per `master.md` (do not hard-code OS paths).
- `${COMMANDS_HOME} = ${CONFIG_ROOT}/commands`
- `${PROFILES_HOME} = ${COMMANDS_HOME}/profiles`
- `${WORKSPACES_HOME} = ${CONFIG_ROOT}/workspaces`

---

## OpenCode Local Configuration (Required for Repo-Aware Mode)

When using this governance system with **OpenCode (repo-aware execution)**,
a **local machine configuration file is REQUIRED** to avoid interactive
path binding and non-deterministic startup behavior.

This repository provides a **template**, not a machine-specific configuration.

### Template (checked in)

```
opencode/opencode.template.json
```

### Local instance (NOT checked in)

Create:

- Linux / macOS: `~/.config/opencode/opencode.json`
- Windows: `%USERPROFILE%\.config\opencode\opencode.json`

### Setup (one-time)

Copy the template and replace placeholders with absolute paths.

Example (Windows):

```json
{
  "paths": {
    "configRoot": "C:/Users/TF81447/.config/opencode",
    "commandsHome": "C:/Users/TF81447/.config/opencode/commands",
    "profilesHome": "C:/Users/TF81447/.config/opencode/commands/profiles",
    "workspacesHome": "C:/Users/TF81447/.config/opencode/workspaces"
  }
}
```

After this, OpenCode will start without any interactive path questions.

**Important:**  
Interactive path binding is intentionally avoided.

---

## Guiding Principle

> Better to block than to guess.  
> Better explicit than implicit.  
> Better governance than speed.

---

_End of file_
