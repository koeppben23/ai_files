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
    # debug fallback only: NOT canonical binding evidence
    def norm(p): return str(p)
    doc={
        'schema':'opencode-governance.paths.v1',
        'status':'blocked',
        'reason_code':'BLOCKED-MISSING-BINDING-FILE',
        'message':'Missing installer-owned governance.paths.json; computed paths are debug-only and non-evidence.',
        'debugComputedPaths':{
            'configRoot': norm(root),
            'commandsHome': norm(root/'commands'),
            'profilesHome': norm(root/'commands'/'profiles'),
            'diagnosticsHome': norm(root/'commands'/'diagnostics'),
            'workspacesHome': norm(root/'workspaces'),
        },
        'recovery_steps':[
            'rerun installer to create commands/governance.paths.json',
            'or provide operator binding evidence plus filesystem proof artifacts',
        ],
        'nonEvidence':'debug-only'
    }
    print(json.dumps(doc,indent=2))"`

## Auto-Persistence Hook (OpenCode)

When available, `/start` triggers a non-destructive workspace persistence backfill helper
to ensure repo-scoped artifacts exist (`repo-cache.yaml`, `repo-map-digest.md`,
`decision-pack.md`, `workspace-memory.yaml`) under `${WORKSPACES_HOME}/<repo_fingerprint>/`.
Fingerprint resolution in the helper follows operational resolution (`--repo-root` first, then global pointer fallback)
for workspace backfill convenience only.

Identity evidence boundary (binding):
- Helper output is operational convenience status only and MUST NOT be treated as canonical repo identity evidence.
- Repo identity remains governed by `master.md` evidence contracts (operator-provided identity evidence or prior validated mapping/session state).
- If identity evidence is missing for the current repo, workflow MUST remain blocked for identity-gated actions.

!`python -c "import os,platform,subprocess,sys,json;from pathlib import Path

def config_root():
    sysname=platform.system()
    if sysname=='Windows':
        up=os.getenv('USERPROFILE')
        if up: return Path(up)/'.config'/'opencode'
        ad=os.getenv('APPDATA')
        if ad: return Path(ad)/'opencode'
        raise SystemExit('Windows: USERPROFILE/APPDATA not set')
    xdg=os.getenv('XDG_CONFIG_HOME')
    return (Path(xdg) if xdg else Path.home()/'.config')/'opencode'

root=config_root(); helper=root/'commands'/'diagnostics'/'persist_workspace_artifacts.py'
if helper.exists():
    run=subprocess.run([sys.executable,str(helper),'--repo-root',str(Path.cwd()),'--quiet'], text=True, capture_output=True, check=False)
    out=(run.stdout or '').strip()
    err=(run.stderr or '').strip()
    if out:
        print(out)
    elif run.returncode==0:
        print(json.dumps({'workspacePersistenceHook':'ok'}))
    else:
        print(json.dumps({'workspacePersistenceHook':'blocked','code':run.returncode,'error':err[:240]}))
else:
    print(json.dumps({'workspacePersistenceHook':'skipped','reason':'helper-missing'}))"`

Binding evidence semantics (binding):
- Only an existing installer-owned `${COMMANDS_HOME}/governance.paths.json` qualifies as canonical binding evidence.
- Fallback computed payloads are debug output only (`nonEvidence`) and MUST NOT be treated as binding evidence.
- If installer-owned binding file is missing, workflow MUST block with `BLOCKED-MISSING-BINDING-FILE` (or `BLOCKED-VARIABLE-RESOLUTION` when variable binding is unresolved).

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

Runtime resolution scope note (binding):
- `/start` enforces installer-owned discovery roots (`${COMMANDS_HOME}`, `${PROFILES_HOME}`) as canonical entrypoint requirements.
- Workspace/local overrides and global fallbacks (`${REPO_OVERRIDES_HOME}`, `${OPENCODE_HOME}`) are runtime resolution extensions governed by `master.md` and MUST NOT weaken this entrypoint contract.

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
- When profile signals are ambiguous, provide a ranked profile shortlist with evidence and request explicit selection (`<recommended> | <alt> | fallback-minimum`) before activation.

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
