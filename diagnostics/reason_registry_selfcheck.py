"""Reason Code Registry Parity Selfcheck.

Validates that reason codes are consistent across:
1. reason_codes.py (constants)
2. reason_codes.registry.json (registry)
3. _embedded_reason_registry.py (embedded mapping)
4. policy-bound diagnostics/*.yaml references (catalogs/routing policies)

Drift between any of these → BLOCKED_ENGINE_SELFCHECK
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def check_reason_registry_parity(repo_root: Path | None = None) -> tuple[bool, list[str]]:
    """Check parity between BLOCKED reason code definitions.
    
    Only checks BLOCKED-* codes, as WARN-* codes are optional in registry.
    
    Args:
        repo_root: Repository root path. If None, tries to detect from file location.
    
    Returns:
        (is_ok, list_of_errors)
    """
    errors: list[str] = []
    
    if repo_root is None:
        # Detect repo root from this file's location
        repo_root = Path(__file__).parent.parent
    
    # Load all three sources
    # 1. reason_codes.py constants (BLOCKED only)
    try:
        from governance.domain import reason_codes
        domain_codes = set(reason_codes.CANONICAL_REASON_CODES)
        # Only check BLOCKED codes (WARN codes are optional in registry)
        domain_blocked = {c for c in domain_codes if c.startswith("BLOCKED-")}
    except Exception as exc:
        errors.append(f"Cannot load reason_codes.py: {exc}")
        return (False, errors)
    
    # 2. reason_codes.registry.json
    registry_path = repo_root / "diagnostics" / "reason_codes.registry.json"
    if not registry_path.exists():
        errors.append(f"Registry file missing: {registry_path}")
        return (False, errors)
    
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry_data = json.load(f)
    except Exception as exc:
        errors.append(f"Cannot parse registry: {exc}")
        return (False, errors)
    
    registry_blocked_codes = set()
    for entry in registry_data.get("blocked_reasons", []):
        if "code" in entry:
            registry_blocked_codes.add(entry["code"])
    
    # 3. _embedded_reason_registry.py
    try:
        from governance.engine._embedded_reason_registry import EMBEDDED_REASON_CODE_TO_SCHEMA_REF
        embedded_codes = set(EMBEDDED_REASON_CODE_TO_SCHEMA_REF.keys())
        embedded_blocked = {c for c in embedded_codes if c.startswith("BLOCKED-")}
    except Exception as exc:
        errors.append(f"Cannot load embedded registry: {exc}")
        return (False, errors)
    
    # Check parity: domain constants ↔ registry (BLOCKED only)
    domain_only = domain_blocked - registry_blocked_codes
    if domain_only:
        errors.append(
            f"Reason codes in reason_codes.py but NOT in registry: {sorted(domain_only)}"
        )
    
    registry_only = registry_blocked_codes - domain_blocked
    if registry_only:
        errors.append(
            f"Reason codes in registry but NOT in reason_codes.py: {sorted(registry_only)}"
        )
    
    # Check parity: domain constants ↔ embedded registry (BLOCKED only)
    embedded_only = embedded_blocked - domain_blocked
    if embedded_only:
        errors.append(
            f"Reason codes in embedded registry but NOT in domain: {sorted(embedded_only)}"
        )
    
    domain_not_embedded = domain_blocked - embedded_blocked
    if domain_not_embedded:
        errors.append(
            f"Reason codes in domain but NOT in embedded registry: {sorted(domain_not_embedded)}"
        )

    # 4. diagnostics/*.yaml references must resolve to registered blocked codes
    yaml_refs: set[str] = set()
    for yaml_path in sorted((repo_root / "diagnostics").glob("*.yaml")):
        try:
            text = yaml_path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Cannot read YAML policy file {yaml_path}: {exc}")
            continue
        for code in re.findall(r"BLOCKED-[A-Z0-9-]+", text):
            yaml_refs.add(code)

    yaml_only = yaml_refs - domain_blocked
    if yaml_only:
        errors.append(
            f"Reason codes in diagnostics/*.yaml but NOT in reason_codes.py: {sorted(yaml_only)}"
        )

    is_ok = len(errors) == 0
    return (is_ok, errors)


def run_reason_registry_selfcheck() -> None:
    """Run selfcheck and print results. Exit 1 on failure."""
    is_ok, errors = check_reason_registry_parity()
    
    if is_ok:
        print("OK: Reason code registry parity verified")
        try:
            from governance.domain.reason_codes import CANONICAL_REASON_CODES
            print(f"  - Domain codes: {len(set(CANONICAL_REASON_CODES))}")
        except Exception:
            pass
        return
    
    print("BLOCKED: Reason code registry parity check failed")
    for error in errors:
        print(f"  - {error}")
    print("Reason: BLOCKED-ENGINE-SELFCHECK")
    raise SystemExit(1)


if __name__ == "__main__":
    run_reason_registry_selfcheck()
