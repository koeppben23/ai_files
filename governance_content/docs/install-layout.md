# Install Layout

This document centralizes install and path layout details moved out of `README.md`.
Runtime authority is `governance_runtime/` + `${LOCAL_ROOT}/governance_spec/phase_api.yaml`; this file is layout guidance.

## Canonical Path Variables

- `${CONFIG_ROOT}`: OpenCode config root (runtime-resolved; do not hard-code OS paths)
- `${LOCAL_ROOT}`: OpenCode local payload root (runtime/content/spec payloads)
- `${COMMANDS_HOME}`: default `${CONFIG_ROOT}/commands` from installer binding evidence
- `${PROFILES_HOME}`: `${LOCAL_ROOT}/governance_content/profiles`
- `${WORKSPACES_HOME}`: default `${CONFIG_ROOT}/workspaces` from installer binding evidence

Supported exception sources (must be explicit and auditable):
- trusted binding override (`OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE=1` + `OPENCODE_TRUSTED_COMMANDS_HOME`)
- controlled dev cwd binding search (`OPENCODE_ALLOW_CWD_BINDINGS=1`)

A common example install root is `~/.config/opencode` (platform-specific variants are resolved via `master.md`).

## Where Files Live

- Config root (`${CONFIG_ROOT}`): `commands/`, `plugins/`, `workspaces/`, `bin/`.
- Local root (`${LOCAL_ROOT}`): `governance_runtime/`, `governance_content/`, `governance_spec/`, `VERSION`.
- The command rail surface is installed under `${COMMANDS_HOME}` as a strict allowlist.
- Profile rulebooks and addon manifests are installed under `${PROFILES_HOME}`.
- Repo-scoped persistent artifacts are stored under `${WORKSPACES_HOME}/<repo_fingerprint>/...`.
- Active session pointer remains global at `${SESSION_STATE_POINTER_FILE}`.
- Canonical session payload is repo-scoped at `${SESSION_STATE_FILE}`.

## Installed Layout (Canonical Shape)

Note: Bootstrap is performed via the local launcher (`${CONFIG_ROOT}/bin/opencode-governance-bootstrap`). Kernel bootstrapping and path resolution are governed by installer binding evidence and kernel loaders.

```text
${CONFIG_ROOT}/
  bin/
    opencode-governance-bootstrap
    opencode-governance-bootstrap.cmd
  plugins/
    audit-new-session.mjs
  commands/
    audit-readout.md
    continue.md
    implement.md
    implementation-decision.md
    plan.md
    review-decision.md
    review.md
    ticket.md
  workspaces/
    <repo_fingerprint>/
      logs/
    _global/
      logs/
  opencode.json
  INSTALL_HEALTH.json
  INSTALL_MANIFEST.json
  governance.paths.json
  SESSION_STATE.json
  governance.activation_intent.json

${LOCAL_ROOT}/
  governance_runtime/
  governance_content/
  governance_spec/
  VERSION
```

## Customer-Facing Installed Assets

After bundle install, operator-usable assets are available under config/local split:

- `<config_root>/commands/`: exactly 8 canonical rail markdown files
- `<config_root>/plugins/`: desktop plugin artifact
- `<config_root>/workspaces/`: repo-scoped and global logs/state
- `<config_root>/workspaces/<repo_fingerprint>/`: workspace directory
  - `governance-config.json` — policy knobs (automatically materialized during bootstrap)
  - `SESSION_STATE.json` — current session state
- `<config_root>/`: `opencode.json`, `INSTALL_HEALTH.json`, `INSTALL_MANIFEST.json`, `governance.paths.json`, `SESSION_STATE.json`, `governance.activation_intent.json`
- `<local_root>/governance_runtime/`: canonical runtime authority
- `<local_root>/governance_content/`: content payload
- `<local_root>/governance_spec/`: spec payload

Markdown shipping exclusions are controlled by `governance_runtime/assets/catalogs/CUSTOMER_MARKDOWN_EXCLUDE.json`.
