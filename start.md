# Governance Start — master invocation

This project uses a formal LLM Governance System
defined in `master.md`, `rules.md`, and profile rulebooks.


## Auto-Binding Evidence (OpenCode)

When executed as an OpenCode command (`/start`), this prompt injects the installer-owned path binding file
`${COMMANDS_HOME}/governance.paths.json` into the model context.

!`python -c "import os,platform,json;from pathlib import Path

def config_root():
    sys=platform.system()
    if sys=='Windows':
        up=os.getenv('USERPROFILE')
        if up: return Path(up)/'.config'/'opencode'
        ad=os.getenv('APPDATA')
        if ad: return Path(ad)/'opencode'
        raise SystemExit('Windows: USERPROFILE/APPDATA not set')
    xdg=os.getenv('XDG_CONFIG_HOME')
    return (Path(xdg) if xdg else Path.home()/'.config')/'opencode'

root=config_root(); f=root/'commands'/'governance.paths.json'
if f.exists():
    print(f.read_text(encoding='utf-8'))
else:
    # last resort: compute the same payload that the installer would write
    def norm(p): return p.as_posix()
    doc={'schema':'opencode-governance.paths.v1','generatedAt':'missing-file','paths':{
        'configRoot': norm(root),
        'commandsHome': norm(root/'commands'),
        'profilesHome': norm(root/'commands'/'profiles'),
        'workspacesHome': norm(root/'workspaces'),
    }}
    print(json.dumps(doc,indent=2))"`

The injected JSON is the canonical binding for `${CONFIG_ROOT}`, `${COMMANDS_HOME}`, `${PROFILES_HOME}`, `${WORKSPACES_HOME}`.
Treat it as **evidence**.

---

## Governance Evidence — Variable Resolution (Binding)

This entrypoint MUST NOT contain OS-specific absolute paths.
All locations MUST be expressed using canonical variables as defined by `master.md`.

Clarification (Binding):
- "This entrypoint" refers ONLY to the `start.md` file content.
- Operator-provided evidence MAY include OS-specific absolute paths when supplied as chat input,
  because they are evidence about the runtime environment, not persisted governance text.

### Required variables (conceptual)
- `${USER_HOME}` (OS-resolved user home)
- `${CONFIG_ROOT}` (OpenCode config root; OS-resolved per master.md)
- `${OPENCODE_HOME} = ${CONFIG_ROOT}`
- `${COMMANDS_HOME} = ${OPENCODE_HOME}/commands`
- `${PROFILES_HOME} = ${COMMANDS_HOME}/profiles`

### Discovery / Load search order (Binding)
The runtime MUST attempt to resolve rulebooks using this search order:
1) `${COMMANDS_HOME}/master.md`
2) `${COMMANDS_HOME}/rules.md`
3) `${PROFILES_HOME}/rules.<profile>.md` OR `${PROFILES_HOME}/rules_<profile>.md` OR `${PROFILES_HOME}/rules-<profile>.md`

### Evidence rule (Binding)
Because this file cannot self-prove filesystem state, governance activation MUST use one of:

A) **Host-provided file access evidence** (preferred)
   - Tool output showing the resolved directory listing for `${COMMANDS_HOME}` and `${PROFILES_HOME}`, OR
   - Tool output confirming reads of `master.md`, `rules.md`, and the selected profile rulebook.

B) **Operator-provided evidence** (fallback, minimal)
   - The operator provides the resolved value for `${COMMANDS_HOME}` as a variable binding via chat input,
     plus ONE proof artifact:
       - either a directory listing showing the files exist, or
       - the full contents of the required rulebooks.

If neither A nor B is available → `BLOCKED` with required input = “Provide variable binding + proof artifact”.
Canonical BLOCKED reason:
- BLOCKED-VARIABLE-RESOLUTION (no resolved value for `${COMMANDS_HOME}`)

Invocation:
- Activate the Governance-OS defined in `master.md`.
- This file does not replace or inline `master.md`; it only triggers its discovery and activation.
- Phases 1–6 are enforced as far as host/system constraints allow.
- Plan-Gates ≠ Evidence-Gates.
- Missing evidence → BLOCKED (reported, not suppressed).
- Profile ambiguity → BLOCKED.

Rulebook discovery contract (BINDING):
- The assistant MUST NOT claim `master.md`, `rules.md`, or profile rulebooks are "missing"
  unless it has explicit load evidence that lookup was attempted in the canonical locations
  OR the operator confirms the files are not present.
- If rulebook contents are not available in the current chat context, treat them as
  `NOT IN PROVIDED SCOPE` and request minimal evidence (path or pasted content).
- Canonical expected locations (per master.md variables):
  - master.md: `${COMMANDS_HOME}/master.md`
  - rules.md: `${COMMANDS_HOME}/rules.md`
  - profiles: `${PROFILES_HOME}/rules*.md`
- If the host cannot access the filesystem, the operator MUST provide one of:
  A) exact resolved paths + confirmation they exist, OR
  B) paste the full file contents for master.md, rules.md, and the selected profile.

Host constraint acknowledgment:
- Host / system / developer instructions may override this governance.
- Any such override MUST be reported explicitly under `DEVIATION`
  (rule/gate + best conforming alternative).

Output requirements:
- Structured, phase-oriented output
- Explicit SESSION_STATE
- Explicit Gates
- Explicit DEVIATION reporting
- No chat-style answers

This file is the canonical governance entrypoint.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — start.md
