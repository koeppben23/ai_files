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
    try:
        print(f.read_text(encoding='utf-8'))
    except Exception as ex:
        print(json.dumps({
            'schema':'opencode-governance.paths.v1',
            'status':'blocked',
            'reason_code':'BLOCKED-VARIABLE-RESOLUTION',
            'message':'Installer-owned governance.paths.json exists but could not be read.',
            'bindingFile': str(f),
            'missing_evidence':['${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)'],
            'error': str(ex)[:240],
            'recovery_steps':[
                'allow OpenCode host read access to governance.paths.json',
                'rerun /start so host-provided binding evidence can be loaded',
            ],
            'next_command':'/start',
            'nonEvidence':'debug-only'
        },indent=2))
else:
    # debug fallback only: NOT canonical binding evidence
    def norm(p): return str(p)
    doc={
        'schema':'opencode-governance.paths.v1',
        'status':'blocked',
        'reason_code':'BLOCKED-MISSING-BINDING-FILE',
        'message':'Missing installer-owned governance.paths.json; computed paths are debug-only and non-evidence.',
        'missing_evidence':['${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)'],
        'next_command':'/start',
        'debugComputedPaths':{
            'configRoot': norm(root),
            'commandsHome': norm(root/'commands'),
            'profilesHome': norm(root/'commands'/'profiles'),
            'diagnosticsHome': norm(root/'commands'/'diagnostics'),
            'workspacesHome': norm(root/'workspaces'),
        },
        'recovery_steps':[
            'rerun installer to create commands/governance.paths.json',
            'rerun /start after installer repair',
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

!`python -c "import os,platform,subprocess,sys,json,importlib.util;from pathlib import Path

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

root=config_root(); diag=root/'commands'/'diagnostics'; helper=diag/'persist_workspace_artifacts.py'; bootstrap=diag/'bootstrap_session_state.py'; logger=diag/'error_logs.py'; identity_map=root/'repo-identity-map.yaml'

def _log(reason_key,message,observed):
    try:
        if not logger.exists():
            return
        spec=importlib.util.spec_from_file_location('opencode_error_logs',str(logger))
        if not spec or not spec.loader:
            return
        mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        fn=getattr(mod,'safe_log_error',None)
        if not callable(fn):
            return
        fn(
            reason_key=reason_key,
            message=message,
            config_root=root,
            phase='1.1-Bootstrap',
            gate='PERSISTENCE',
            mode='repo-aware',
            command='start.md:/start',
            component='workspace-persistence-hook',
            observed_value=observed,
            expected_constraint='persist_workspace_artifacts.py available and returns code 0',
            remediation='Reinstall governance package and rerun /start.'
        )
    except Exception:
        pass

if helper.exists():
    if not identity_map.exists():
        _log('ERR-WORKSPACE-PERSISTENCE-SKIPPED-NO-IDENTITY-EVIDENCE','/start workspace persistence skipped because repo identity map evidence is missing.',{'identityMap':str(identity_map)})
        print(json.dumps({'workspacePersistenceHook':'warn','reason_code':'WARN-WORKSPACE-PERSISTENCE','reason':'skipped-no-identity-evidence','impact':'no repo-scoped persistence without validated identity evidence','required_operator_action':'run bootstrap_session_state.py with explicit repo fingerprint, then rerun /start','feedback_required':'reply with the repo fingerprint used and whether bootstrap_session_state.py succeeded','next_command':'python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint> --repo-name <repo_name>'}))
        raise SystemExit(0)
    run=subprocess.run([sys.executable,str(helper),'--repo-root',str(Path.cwd()),'--quiet'], text=True, capture_output=True, check=False)
    out=(run.stdout or '').strip()
    err=(run.stderr or '').strip()
    if run.returncode==0 and out:
        try:
            payload=json.loads(out)
        except Exception:
            payload=None
        if isinstance(payload,dict) and payload.get('sessionStateUpdate')=='no-session-file' and bootstrap.exists():
            fp=str(payload.get('repoFingerprint') or '').strip()
            if fp:
                b_run=subprocess.run([sys.executable,str(bootstrap),'--repo-fingerprint',fp,'--config-root',str(root)], text=True, capture_output=True, check=False)
                if b_run.returncode==0:
                    print(json.dumps({'workspacePersistenceHook':'ok','bootstrapSessionState':'created','repoFingerprint':fp}))
                else:
                    b_err=(b_run.stderr or '')[:240]
                    _log('ERR-SESSION-BOOTSTRAP-HOOK-FAILED','/start session bootstrap helper returned non-zero.',{'repoFingerprint':fp,'stderr':b_err})
                    print(json.dumps({'workspacePersistenceHook':'warn','reason_code':'WARN-WORKSPACE-PERSISTENCE','reason':'bootstrap-session-failed','repoFingerprint':fp,'error':b_err,'impact':'repo-scoped SESSION_STATE may be incomplete','recovery':'python diagnostics/bootstrap_session_state.py --repo-fingerprint <repo_fingerprint>'}))
            else:
                print(out)
        elif isinstance(payload,dict) and payload.get('status')=='blocked':
            _log('ERR-WORKSPACE-PERSISTENCE-HOOK-BLOCKED','/start workspace persistence helper reported blocked output.',payload)
            print(json.dumps({'workspacePersistenceHook':'warn','reason_code':'WARN-WORKSPACE-PERSISTENCE','reason':'helper-reported-blocked','helperPayload':payload,'impact':'workspace artifacts may be incomplete','recovery':'python diagnostics/persist_workspace_artifacts.py --repo-root <repo_root>'}))
        else:
            print(out)
    elif run.returncode==0:
        print(json.dumps({'workspacePersistenceHook':'ok'}))
    else:
        _log('ERR-WORKSPACE-PERSISTENCE-HOOK-FAILED','/start workspace persistence helper returned non-zero.',{'returncode':run.returncode,'stderr':err[:240]})
        print(json.dumps({'workspacePersistenceHook':'warn','reason_code':'WARN-WORKSPACE-PERSISTENCE','reason':'helper-failed','code':run.returncode,'error':err[:240],'impact':'workspace artifacts may be incomplete','recovery':'python diagnostics/persist_workspace_artifacts.py --repo-root <repo_root>'}))
else:
    _log('ERR-WORKSPACE-PERSISTENCE-HOOK-MISSING','/start workspace persistence helper is missing from diagnostics payload.',{'helper':str(helper)})
    print(json.dumps({'workspacePersistenceHook':'warn','reason_code':'WARN-WORKSPACE-PERSISTENCE','reason':'helper-missing','impact':'workspace artifacts may be incomplete','recovery':'python diagnostics/persist_workspace_artifacts.py --repo-root <repo_root>'}))"`

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
   - Tool output confirming reads of `master.md` (and top-tier bootstrap artifacts when present); `rules.md` load evidence is deferred until Phase 4.

Binding behavior (MUST):
- If installer-owned `${COMMANDS_HOME}/governance.paths.json` exists and host filesystem tools are available,
  `/start` MUST attempt host-provided evidence first and MUST NOT request operator-provided variable binding before that attempt.

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
- `/start` is mandatory bootstrap for a repo/session.
- In hosts that support `/master`: `/master` without valid `/start` evidence MUST map to `BLOCKED-START-REQUIRED` with `QuickFixCommands: ["/start"]`.
- OpenCode Desktop mapping (host-constrained): `/start` acts as the `/master`-equivalent and performs the ARCHITECT master-run inline.
- Canonical operator lifecycle (OpenCode Desktop): `/start` (bootstrap + ARCHITECT master-run) -> `Implement now` (IMPLEMENT) -> `Ingest evidence` (VERIFY).
- Plan-Gates ≠ Evidence-Gates.
- Missing evidence → BLOCKED (reported, not suppressed).
- Profile ambiguity → BLOCKED.
- `/start` MUST NOT require explicit profile selection to complete bootstrap when `master.md` bootstrap evidence is available; profile selection remains a Phase 1.2/Post-Phase-2 concern.
- When profile signals are ambiguous, provide a ranked profile shortlist with evidence and request explicit numbered selection (`1=<recommended> | 2=<alt> | 3=<alt> | 4=fallback-minimum | 0=abort/none`) before activation.

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
- Output envelope SHOULD comply with `diagnostics/RESPONSE_ENVELOPE_SCHEMA.json` (`status`, `session_state`, `next_action`, `snapshot`; plus blocker payload fields when blocked) when host constraints allow
- Explicit SESSION_STATE
- Explicit Gates
- Explicit DEVIATION reporting
- Prefer structured (non-chat) answers when host constraints allow
- End every response with `[NEXT-ACTION]` footer (`Status`, `Next`, `Why`, `Command`) per `master.md` when host constraints allow
- If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`) when host constraints allow
- At session start, include `[START-MODE] Cold Start | Warm Start - reason: ...` based on discovery artifact validity evidence.
- Include `[SNAPSHOT]` block (`Confidence`, `Risk`, `Scope`) with values aligned to current `SESSION_STATE`.
- If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `["none"]` if not command-driven) when host constraints allow.
- If strict output formatting is host-constrained, response MUST include COMPAT sections: `RequiredInputs`, `Recovery`, and `NextAction` and set `DEVIATION.host_constraint = true`.

This file is the canonical governance entrypoint.

---

Copyright © 2026 Benjamin Fuchs.
All rights reserved. See LICENSE.

END OF FILE — start.md
