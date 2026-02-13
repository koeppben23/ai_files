# Install Layout

This document centralizes install and path layout details moved out of `README.md`.
`master.md` remains authoritative for variable binding and precedence.

## Canonical Path Variables

- `${CONFIG_ROOT}`: OpenCode config root (runtime-resolved; do not hard-code OS paths)
- `${COMMANDS_HOME} = ${CONFIG_ROOT}/commands`
- `${PROFILES_HOME} = ${COMMANDS_HOME}/profiles`
- `${WORKSPACES_HOME} = ${CONFIG_ROOT}/workspaces`

A common example install root is `~/.config/opencode` (platform-specific variants are resolved via `master.md`).

## Where Files Live

- Global rulebooks are installed under `${COMMANDS_HOME}`.
- Profile rulebooks and addon manifests are installed under `${PROFILES_HOME}`.
- Repo-scoped persistent artifacts are stored under `${WORKSPACES_HOME}/<repo_fingerprint>/...`.
- Active session pointer remains global at `${SESSION_STATE_POINTER_FILE}`.
- Canonical session payload is repo-scoped at `${SESSION_STATE_FILE}`.

## Installed Layout (Canonical Shape)

Note: AGENTS.md is a frontend surface; kernel bootstrapping and path resolution remain governed by master.md and start.md. The runtime config root and path variables are resolved at runtime as described in master.md; AGENTS.md presence does not alter OpenCode path resolution.

```text
${COMMANDS_HOME}/
  master.md
  rules.md
  start.md
  continue.md
  resume.md
  README.md
  README-RULES.md
  README-OPENCODE.md
  SESSION_STATE_SCHEMA.md
  STABILITY_SLA.md
  CONFLICT_RESOLUTION.md
  governance.paths.json
  INSTALL_MANIFEST.json
  profiles/
    rules.<stack>.md
    addons/*.addon.yml
  diagnostics/
  governance/
  scripts/
  templates/
```

## Customer-Facing Installed Assets

After `install.py`, customer-usable assets are available under `<config_root>/commands/`:

- `scripts/`: customer-approved script catalog entries
- `templates/<family>/`: shipped workflow template families
- `profiles/`: profile rulebooks and addon manifests
- `diagnostics/`: schemas, benchmark packs, and helper diagnostics

Markdown shipping exclusions are controlled by `diagnostics/CUSTOMER_MARKDOWN_EXCLUDE.json`.
