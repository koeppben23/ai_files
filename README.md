
- Deterministic phase workflow (`1` through `6`) with explicit gate outcomes.
- Repo-aware governance runtime under `governance/` with tested fail-closed semantics.
- Installer and customer handoff flow (bundle installers, release/bundle docs).
- Governance schema and policy contracts under `governance/`.
- Profile and addon ecosystem under `profiles/`.

## Quick Start

- Install from the customer bundle (`install.sh` or `install.ps1`)
- Verify installation with the bundle installer `--status`
- Run the local bootstrap launcher to start a governed session (with `--repo-root`)
- Use `--verbose` on bootstrap when you need step-by-step flow output
- Open OpenCode Desktop in the same repository and run `/continue`
- Use `/resume` only for explicit interrupted-session recovery

For OpenCode Desktop lifecycle and command details, see `README-OPENCODE.md`.

Bundle install (example):

```bash
unzip customer-install-bundle-v1.zip
cd customer-install-bundle-v1
./install/install.sh --status
```

Note: installer-owned path binding evidence is written to `<config_root>/commands/governance.paths.json` and is required for canonical OpenCode bootstrap behavior.
Preflight records only raw tool availability (BuildToolchain snapshot); repo-specific build mapping happens later in Phase 2.


## 60-Second Install Verification

Run the following after installation:

```bash
# macOS / Linux (from extracted bundle)
./install/install.sh --status
./install/install.sh --smoketest
```

```powershell
# Windows (from extracted bundle)
.\install\install.ps1 --status
.\install\install.ps1 --smoketest
```

Expected outcome:

- install run completes without blocker reason codes.
- `--status` reports installed governance assets and healthy path bindings.


## Troubleshooting

- `BLOCKED-MISSING-BINDING-FILE`: rerun the bundle installer, then verify with `--status`.
- `BLOCKED-VARIABLE-RESOLUTION`: check resolved config root/path bindings against `docs/install-layout.md`.
- `BLOCKED-REPO-IDENTITY-RESOLUTION`: ensure repository is a git checkout and `git` is available in `PATH`.
- `NOT_VERIFIED-MISSING-EVIDENCE`: provide missing evidence artifacts and rerun the gate.
