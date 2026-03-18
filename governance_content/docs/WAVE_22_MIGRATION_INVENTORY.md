# Wave 22 - Runtime Migration Inventory

## Migration Map

### Phase 1: Root-level directories → governance_runtime/

| Source | Target | Status |
|--------|--------|--------|
| `cli/*` | `governance_runtime/cli/*` | TODO |
| `bin/*` | `governance_runtime/bin/*` | TODO |
| `session_state/*` | `governance_runtime/session_state/*` | TODO |
| `governance/application/*` | `governance_runtime/application/*` | TODO |
| `governance/domain/*` | `governance_runtime/domain/*` | TODO |
| `governance/engine/*` | `governance_runtime/engine/*` | TODO |
| `governance/infrastructure/*` | `governance_runtime/infrastructure/*` | TODO |
| `governance/kernel/*` | `governance_runtime/kernel/*` | TODO |

### Phase 2: Special files

| Source | Target | Status |
|--------|--------|--------|
| `install.py` | `governance_runtime/install/install.py` | TODO |

## Identified Hotspots

### Runtime Imports (must stay compatible during transition)
- `from governance import *` - many consumers
- `import governance.kernel.*` - kernel imports
- `from governance.infrastructure import *` - infrastructure imports

### Test Imports (must be updated)
- `tests/util.py` - SSOT helpers reference governance paths
- `tests/conformance/*` - various governance imports

### CLI Entrypoints (must be updated)
- `bin/opencode-governance-bootstrap` - currently references cli/
- `bin/opencode-governance-bootstrap.cmd` - Windows variant

### Installer/Packaging
- `install.py` - root-level installer
- `scripts/release.py` - release scripts

## Compatibility Strategy

During transition (Wave 22-26):
1. Keep import aliases at old locations pointing to new
2. Update all consumers incrementally
3. Remove aliases in Wave 26 (Root-Bridges removal)

## Target Structure (after migration)

```
governance_runtime/
├── __init__.py           # Main package init
├── application/          # From governance/application/
├── domain/              # From governance/domain/
├── engine/              # From governance/engine/
├── infrastructure/      # From governance/infrastructure/
├── kernel/              # From governance/kernel/
├── cli/                 # From cli/
├── bin/                 # From bin/
├── session_state/       # From session_state/
├── install/             # From install.py (as install.py)
└── scripts/             # Existing governance_runtime/scripts/
```

## Risk Assessment

### High Risk
- Import chain breakage across entire codebase
- CLI entrypoint failure
- Test suite breakage

### Medium Risk
- Installer path references
- Release/packaging scripts

### Low Risk
- Documentation references (can be updated later)

## Next Steps (Wave 22b)
1. Physically move directories
2. Update all imports
3. Fix CLI entrypoints
4. Run comprehensive test suite
