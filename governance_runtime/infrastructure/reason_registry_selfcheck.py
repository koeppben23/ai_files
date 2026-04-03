"""Reason code registry parity selfcheck implementation."""

from __future__ import annotations

import json
import re
from pathlib import Path


def check_reason_registry_parity(repo_root: Path | None = None) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if repo_root is None:
        repo_root = Path(__file__).absolute().parents[2]

    try:
        from governance_runtime.domain import reason_codes

        domain_codes = set(reason_codes.CANONICAL_REASON_CODES)
        domain_blocked = {c for c in domain_codes if c.startswith("BLOCKED-")}
    except (ImportError, AttributeError) as exc:
        errors.append(f"Cannot load reason_codes.py: {exc}")
        return (False, errors)

    registry_path = repo_root / "governance_runtime" / "assets" / "catalogs" / "reason_codes.registry.json"
    if not registry_path.exists():
        errors.append(f"Registry file missing: {registry_path}")
        return (False, errors)

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry_data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Cannot parse registry: {exc}")
        return (False, errors)

    blocked_entries = registry_data.get("blocked_reasons", [])
    if not isinstance(blocked_entries, list):
        errors.append("Registry blocked_reasons must be an array")
        return (False, errors)

    registry_blocked_codes = set()
    non_blocked_entries: list[str] = []
    for entry in blocked_entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code", "")).strip()
        if not code:
            continue
        if code.startswith("BLOCKED-"):
            registry_blocked_codes.add(code)
        else:
            non_blocked_entries.append(code)

    if non_blocked_entries:
        errors.append(
            "Registry blocked_reasons contains non-BLOCKED codes: "
            f"{sorted(non_blocked_entries)}"
        )

    try:
        from governance_runtime.engine._embedded_reason_registry import EMBEDDED_REASON_CODE_TO_SCHEMA_REF

        embedded_codes = set(EMBEDDED_REASON_CODE_TO_SCHEMA_REF.keys())
        embedded_blocked = {c for c in embedded_codes if c.startswith("BLOCKED-")}
    except (ImportError, AttributeError) as exc:
        errors.append(f"Cannot load embedded registry: {exc}")
        return (False, errors)

    domain_only = domain_blocked - registry_blocked_codes
    if domain_only:
        errors.append(f"Reason codes in reason_codes.py but NOT in registry: {sorted(domain_only)}")

    registry_only = registry_blocked_codes - domain_blocked
    if registry_only:
        errors.append(f"Reason codes in registry but NOT in reason_codes.py: {sorted(registry_only)}")

    embedded_only = embedded_blocked - domain_blocked
    if embedded_only:
        errors.append(f"Reason codes in embedded registry but NOT in domain: {sorted(embedded_only)}")

    domain_not_embedded = domain_blocked - embedded_blocked
    if domain_not_embedded:
        errors.append(f"Reason codes in domain but NOT in embedded registry: {sorted(domain_not_embedded)}")

    yaml_refs: set[str] = set()
    for yaml_path in sorted((repo_root / "governance_runtime" / "assets" / "config").glob("*.yaml")):
        try:
            text = yaml_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Cannot read YAML policy file {yaml_path}: {exc}")
            continue
        for code in re.findall(r"BLOCKED-[A-Z0-9-]+", text):
            yaml_refs.add(code)

    yaml_only = yaml_refs - domain_blocked
    if yaml_only:
        errors.append(f"Reason codes in governance_runtime/assets/config/*.yaml but NOT in reason_codes.py: {sorted(yaml_only)}")

    return (len(errors) == 0, errors)


def run_reason_registry_selfcheck() -> None:
    is_ok, errors = check_reason_registry_parity()
    if is_ok:
        print("OK: Reason code registry parity verified")
        return
    print("BLOCKED: Reason code registry parity check failed")
    for error in errors:
        print(f"  - {error}")
    print("Reason: BLOCKED-ENGINE-SELFCHECK")
    raise SystemExit(1)
