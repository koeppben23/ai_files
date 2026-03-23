## What this project provides

- Deterministic governance workflow (Phases 1-6) with explicit gate outcomes
- Canonical runtime authority under `governance_runtime/`
- Canonical docs and operator rails under `governance_content/`
- Canonical policy/spec artifacts under `governance_spec/`
- OpenCode launcher and command surfaces for governed session execution

## Quick Install

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

## Next Steps

**Full documentation:** [DOCS.md](DOCS.md)

## Repository Layout

```
governance_runtime/  # runtime authority (kernel, application, infrastructure)
governance_content/  # operator docs and command rails
governance_spec/     # policy/spec source of truth
```
