## What this bundle provides

- Deterministic governance workflow (Phases 1-6) with explicit gate outcomes.
- Installer-managed runtime and policy assets under `governance/`.
- OpenCode launcher and command surfaces for governed session execution.
- Profile and addon support under `profiles/`.

## Install

```bash
unzip customer-install-bundle-v1.zip
cd customer-install-bundle-v1
./install/install.sh
```

```powershell
Expand-Archive -Path customer-install-bundle-v1.zip -DestinationPath .
cd customer-install-bundle-v1
.\install\install.ps1
```

## Verify

```bash
./install/install.sh --status
./install/install.sh --smoketest
```

```powershell
.\install\install.ps1 --status
.\install\install.ps1 --smoketest
```

`governance.paths.json` under `<config_root>/commands/` is required for canonical bootstrap behavior.

## Start a governed session

1. Run bootstrap launcher with repo root:
   - `opencode-governance-bootstrap --repo-root <repo-root>`
   - `opencode-governance-bootstrap.cmd --repo-root <repo-root>`
2. Open OpenCode Desktop in the same repository and run `/continue`.
3. For new work at Phase 4, run `/ticket`, then `/plan`.
4. Use `/review` as a read-only rail entrypoint for review-depth feedback.

## Docs and troubleshooting

- OpenCode lifecycle: `README-OPENCODE.md`
- Quickstart: `QUICKSTART.md`
- Rules overview: `README-RULES.md`
- Install path binding details: `docs/install-layout.md`

## Uninstall

Current stable public uninstall surface:

```bash
python install.py --uninstall --force
```

This is the currently supported remove operation until bundle-level uninstall surface is explicitly marked stable.

Uninstall removes installer-owned governance files and runtime state, and preserves:
- opencode.json
- `governance.paths.json` (unless `--purge-paths-file` is passed)
- Non-governance user-owned files
