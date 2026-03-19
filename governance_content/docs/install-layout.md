# Install Layout

This document centralizes install and path layout details moved out of `README.md`.
Runtime authority is `governance_runtime/` + `${COMMANDS_HOME}/phase_api.yaml`; this file is layout guidance.

## Canonical Path Variables

- `${CONFIG_ROOT}`: OpenCode config root (runtime-resolved; do not hard-code OS paths)
- `${LOCAL_ROOT}`: OpenCode local payload root (runtime/content/spec/compatibility payloads)
- `${COMMANDS_HOME}`: default `${CONFIG_ROOT}/commands` from installer binding evidence
- `${PROFILES_HOME}`: `${COMMANDS_HOME}/profiles`
- `${WORKSPACES_HOME}`: default `${CONFIG_ROOT}/workspaces` from installer binding evidence

Supported exception sources (must be explicit and auditable):
- trusted binding override (`OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE=1` + `OPENCODE_TRUSTED_COMMANDS_HOME`)
- controlled dev cwd binding search (`OPENCODE_ALLOW_CWD_BINDINGS=1`)

A common example install root is `~/.config/opencode` (platform-specific variants are resolved via `master.md`).

## Where Files Live

- Config root (`${CONFIG_ROOT}`): `commands/`, `plugins/`, `workspaces/`, `bin/`.
- Local root (`${LOCAL_ROOT}`): `governance_runtime/`, `governance_content/`, `governance_spec/`, `governance/`, `VERSION`.
- Global rulebooks/rails are installed under `${COMMANDS_HOME}`.
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
  master.md
  rules.md
  BOOTSTRAP.md
  continue.md
  review.md
  docs/resume.md                 # legacy compatibility alias for /continue guidance
  docs/resume_prompt.md          # deprecated template alias (use /continue)
  README.md
  README-RULES.md
  README-OPENCODE.md
  SESSION_STATE_SCHEMA.md
  STABILITY_SLA.md
  CONFLICT_RESOLUTION.md
  governance.paths.json
  INSTALL_MANIFEST.json
  INSTALL_HEALTH.json
  profiles/
    rules.<stack>.md
    addons/*.addon.yml
  workspaces/
    <repo_fingerprint>/
      logs/
    _global/
      logs/

${LOCAL_ROOT}/
  governance_runtime/
  governance_content/
  governance_spec/
  governance/
  VERSION
```

## Customer-Facing Installed Assets

After bundle install, operator-usable assets are available under config/local split:

- `<config_root>/commands/`: rails, normative docs, profiles
- `<config_root>/plugins/`: desktop plugin artifact
- `<config_root>/workspaces/`: repo-scoped and global logs/state
- `<local_root>/governance_runtime/`: canonical runtime authority
- `<local_root>/governance_content/`: content payload
- `<local_root>/governance_spec/`: spec payload
- `<local_root>/governance/`: compatibility-only payload

Markdown shipping exclusions are controlled by `governance/assets/catalogs/CUSTOMER_MARKDOWN_EXCLUDE.json`.
