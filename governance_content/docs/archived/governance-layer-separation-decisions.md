# Governance Layer Separation - Decision Freeze

> This document captures the binding architectural decisions for the governance layer separation project.
> All subsequent waves must adhere to these decisions.

## Decision F0: Architecture Freeze

### 1. Command Surface (Final)

**command_yes** (canonical slash commands):
- `continue.md`
- `plan.md`
- `review.md`
- `review-decision.md`
- `ticket.md`
- `implement.md`
- `implementation-decision.md`
- `audit-readout.md`

**command_no** (non-command content):
- `rules.md` - governance rulebook, NOT a command
- `master.md` - governance master guidance, NOT a command
- `docs/new_profile.md` - factory content, NOT a canonical slash command
- `docs/new_addon.md` - factory content, NOT a canonical slash command
- `docs/resume.md` - legacy alias guidance
- `docs/resume_prompt.md` - legacy alias guidance

### 2. Version SSOT

- Single source of truth for version: `VERSION` at repository root
- Legacy VERSION path in the former governance namespace is deprecated and should be removed

### 3. Logging Rule (Hard)

- Logs MUST only reside under `workspaces/<fp>/logs/`
- No global `logs/` directory for runtime logs
- `commands/logs/` is deprecated

### 4. Layer Definitions

| Layer | Contents | Install Target |
|-------|----------|---------------|
| opencode_command | 8 canonical rails | `~/.config/opencode/commands/` |
| opencode_plugin | Desktop plugins | `~/.config/opencode/plugins/` |
| opencode_config | Configuration | `~/.config/opencode/` |
| governance_runtime | Python/code runtime | `<governance_runtime_root>/` |
| governance_static_content | Docs/profiles/templates | `<governance_content_root>/` |
| governance_spec | Machine SSOT (yaml/json) | `<governance_spec_root>/` |
| repo_run_state | Workspace state/logs | `~/.config/opencode/workspaces/<fp>/` |

### 5. Hard Rules

1. Only canonical slash commands in OpenCode command surface
2. `rules.md` and `master.md` are content, NOT commands
3. Runtime code must NOT live in command surface
4. Spec must be separate from content
5. Logs must live only under `workspaces/<fp>/logs/`
6. Static install content and runtime state must never be mixed

---

## Change History

| Date | Decision | Author |
|------|----------|--------|
| 2026-03-17 | Initial freeze | Architecture |
