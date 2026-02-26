# Install Layout

This document centralizes install and path layout details moved out of `README.md`.
Runtime authority is kernel + `${COMMANDS_HOME}/phase_api.yaml`; this file is layout guidance.

## Canonical Path Variables

- `${CONFIG_ROOT}`: OpenCode config root (runtime-resolved; do not hard-code OS paths)
- `${COMMANDS_HOME}`: default `${CONFIG_ROOT}/commands` from installer binding evidence
- `${PROFILES_HOME}`: `${COMMANDS_HOME}/profiles`
- `${WORKSPACES_HOME}`: default `${CONFIG_ROOT}/workspaces` from installer binding evidence

Supported exception sources (must be explicit and auditable):
- trusted binding override (`OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE=1` + `OPENCODE_TRUSTED_COMMANDS_HOME`)
- controlled dev cwd binding search (`OPENCODE_ALLOW_CWD_BINDINGS=1`)

A common example install root is `~/.config/opencode` (platform-specific variants are resolved via `master.md`).

## Where Files Live

- Global rulebooks are installed under `${COMMANDS_HOME}`.
- Profile rulebooks and addon manifests are installed under `${PROFILES_HOME}`.
- Repo-scoped persistent artifacts are stored under `${WORKSPACES_HOME}/<repo_fingerprint>/...`.
- Active session pointer remains global at `${SESSION_STATE_POINTER_FILE}`.
- Canonical session payload is repo-scoped at `${SESSION_STATE_FILE}`.

## Installed Layout (Canonical Shape)

Note: Bootstrap is performed via the local launcher (`${CONFIG_ROOT}/bin/opencode-governance-bootstrap`). Kernel bootstrapping and path resolution are governed by installer binding evidence and kernel loaders.

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
  governance/
  governance/
  scripts/
  templates/
```

## Customer-Facing Installed Assets

After `install.py`, customer-usable assets are available under `<config_root>/commands/`:

- `scripts/`: customer-approved script catalog entries
- `templates/<family>/`: shipped workflow template families
- `profiles/`: profile rulebooks and addon manifests
- `governance/`: schemas, benchmark packs, and helper governance

Markdown shipping exclusions are controlled by `governance/CUSTOMER_MARKDOWN_EXCLUDE.json`.
