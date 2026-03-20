# Block 9 Inventory (Repo Hygiene / Dedup / Archive / Marker Sweep)

This inventory is the Block 9A baseline. Every listed group is classified once with a concrete action.

Legend:
- `K1`: canonical keep
- `K2`: thin wrapper keep
- `K3`: archive to non-productive area
- `K4`: delete
- `K5`: consolidate into one implementation

## Duplicate Groups

| Group | Category | Rationale | Action |
| --- | --- | --- | --- |
| `bin/opencode-governance-bootstrap` + `governance_runtime/bin/opencode-governance-bootstrap` | K5 | Byte-identical launcher duplicates | Canonical: `bin/*`; remove runtime duplicate |
| `bin/opencode-governance-bootstrap.cmd` + `governance_runtime/bin/opencode-governance-bootstrap.cmd` | K5 | Byte-identical launcher duplicates | Canonical: `bin/*`; remove runtime duplicate |
| `cli/deps.py` + `governance_runtime/cli/deps.py` | K5 | Duplicate implementation | Canonical: `governance_runtime/cli/deps.py`; remove root duplicate |
| `session_state/schema.py` + `governance_runtime/session_state/schema.py` | K5 | Duplicate implementation | Canonical: `governance_runtime/session_state/schema.py`; remove root duplicate |
| `session_state/serde.py` + `governance_runtime/session_state/serde.py` | K5 | Duplicate implementation | Canonical: `governance_runtime/session_state/serde.py`; remove root duplicate |
| `session_state/transitions.py` + `governance_runtime/session_state/transitions.py` | K5 | Duplicate implementation | Canonical: `governance_runtime/session_state/transitions.py`; remove root duplicate |
| `governance_content/governance/assets/catalogs/audit.md` + `governance_runtime/assets/catalogs/audit.md` | K5 | Duplicate payload authority | Canonical: `governance_runtime/assets/catalogs/audit.md`; remove content duplicate |
| `governance_runtime/assets/config/blocked_reason_catalog.yaml` + `governance_runtime/assets/reasons/blocked_reason_catalog.yaml` | K5 | Duplicate reason catalog authority | Canonical: `governance_runtime/assets/config/blocked_reason_catalog.yaml`; remove reasons duplicate |
| `governance_content/governance/assets/catalogs/SSOT_GUARD_RULES.json` | K5 | Residual nested legacy subtree path in active guard wiring | Move to canonical catalog location and repoint `scripts/ssot_guard.py` |

## README / Rule Docs

| Group | Category | Rationale | Action |
| --- | --- | --- | --- |
| `README-OPENCODE.md` + `governance_content/README-OPENCODE.md` | K5 | Competing lifecycle docs | Canonical: `README-OPENCODE.md`; remove content mirror |
| `README-RULES.md` + `governance_content/README-RULES.md` | K5 | Root file is canonical summary, content file is shim | Canonical: `README-RULES.md`; remove content mirror |
| Additional `README*.md` and `QUICKSTART*.md` mirrors | K1/K4 by file | Only one truth per surface | Keep canonical files, delete mirrors |

## Archive Surfaces

| Group | Category | Rationale | Action |
| --- | --- | --- | --- |
| `governance_content/docs/archived/**` | K3 | Historical docs in live content tree | Move to non-productive archive area or remove |
| `governance_spec/migrations/archived/**` | K3 | Historical migration docs in live spec tree | Move to non-productive archive area or remove |

## Marker / Pseudo Structure

| Group | Category | Rationale | Action |
| --- | --- | --- | --- |
| `opencode/config/` (marker-only) | K4 | Pseudo-structure without implementation | Remove directory and references |
| `opencode/plugins/` (marker-only) | K4 | Pseudo-structure without implementation | Remove directory and references |

## __init__.py Policy Baseline (to be reduced)

Files below are marker-only today and must be justified or removed in Block 9F:

- `governance_content/reference/__init__.py`
- `governance_runtime/assets/__init__.py`
- `governance_runtime/assets/catalogs/__init__.py`
- `governance_runtime/assets/config/__init__.py`
- `governance_runtime/assets/reasons/__init__.py`
- `governance_runtime/assets/schemas/__init__.py`
- `governance_runtime/bin/__init__.py`
- `governance_runtime/entrypoints/__init__.py`
- `governance_runtime/entrypoints/errors/__init__.py`
- `governance_runtime/entrypoints/io/__init__.py`
- `governance_runtime/install/__init__.py`
- `governance_runtime/scripts/__init__.py`
- `governance_runtime/session_state/__init__.py`
- `governance_spec/config/__init__.py`
- `governance_spec/contracts/__init__.py`
- `governance_spec/schemas/__init__.py`
- `opencode/__init__.py`
- `opencode/commands/__init__.py`
- `opencode/config/__init__.py`
- `opencode/plugins/__init__.py`
- `tests/__init__.py`
- `tests/conformance/__init__.py`

## Guard Scope Introduced in Commit 1

- `scripts/repo_hygiene_guard.py` enforces a fail-closed baseline:
  - no new byte-identical duplicate groups
  - no new `archived/` files in live trees
  - no new README/RULES mirror files
  - no new marker-only `__init__.py`

Baseline entries are intentionally explicit so each cleanup commit can remove items and tighten the guard until the baseline reaches zero debt.
