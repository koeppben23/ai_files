from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, MutableMapping

_RESOLVED_OUTCOMES = {"extracted", "not-applicable", "deferred", "skipped"}


def _parse_bool(token: str) -> bool:
    value = token.strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _parse_status_fields(content: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_token = key.strip().lower()
        if not key_token:
            continue
        fields[key_token] = value.strip()
    return fields


def _parse_inventory_rules(content: str) -> list[str]:
    rules: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("- ") and len(line) > 2:
            candidate = line[2:].strip()
            if _is_valid_rule(candidate):
                rules.append(candidate)
            continue
        if line.startswith("Rule:"):
            value = line[len("Rule:") :].strip()
            if _is_valid_rule(value):
                rules.append(value)
    return rules


def _is_valid_rule(rule: str) -> bool:
    token = " ".join(str(rule or "").strip().split())
    if not token:
        return False
    if not re.match(r"^BR-[A-Za-z0-9._-]+:\s+\S", token):
        return False
    lower = token.lower()
    if "tests/" in lower or "artifacts/" in lower:
        return False
    if re.search(r"\b[a-z0-9_/.-]+\.(py|js|ts|java|md):\d+", lower):
        return False
    if any(ch in token for ch in ("`", "[", "]")):
        return False
    return True


def hydrate_business_rules_state_from_artifacts(
    *,
    state: MutableMapping[str, object],
    status_path: Path,
    inventory_path: Path,
) -> bool:
    """Hydrate ``SESSION_STATE.BusinessRules`` from persisted artifacts.

    Returns True when artifact state was applied, otherwise False.
    """

    if not status_path.exists() or not status_path.is_file():
        return False
    try:
        status_text = status_path.read_text(encoding="utf-8")
    except Exception:
        return False

    status_fields = _parse_status_fields(status_text)
    outcome = status_fields.get("outcome", "").strip().lower()
    execution_evidence = _parse_bool(status_fields.get("executionevidence", "false"))
    if not outcome:
        return False

    inventory_loaded = False
    inventory_rules: list[str] = []
    inventory_sha = "0" * 64
    if inventory_path.exists() and inventory_path.is_file():
        try:
            inventory_text = inventory_path.read_text(encoding="utf-8")
            inventory_loaded = True
            inventory_rules = _parse_inventory_rules(inventory_text)
            normalized = inventory_text if inventory_text.endswith("\n") else inventory_text + "\n"
            inventory_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except Exception:
            inventory_loaded = False
            inventory_rules = []

    extracted_count = len(inventory_rules)

    if outcome == "extracted" and (not execution_evidence or not inventory_loaded or extracted_count <= 0):
        return False

    scope_obj = state.get("Scope")
    scope = dict(scope_obj) if isinstance(scope_obj, dict) else {}
    if outcome in _RESOLVED_OUTCOMES:
        scope["BusinessRules"] = outcome
    state["Scope"] = scope

    business_obj = state.get("BusinessRules")
    business_rules: dict[str, Any] = dict(business_obj) if isinstance(business_obj, dict) else {}
    business_rules["Outcome"] = outcome
    business_rules["ExecutionEvidence"] = execution_evidence
    business_rules["InventoryLoaded"] = bool(inventory_loaded)
    business_rules["ExtractedCount"] = extracted_count
    business_rules["Inventory"] = {
        "sha256": inventory_sha,
        "count": extracted_count,
    }
    if inventory_loaded:
        business_rules["InventoryFileStatus"] = "written"
        business_rules["InventoryFileMode"] = "update"
        business_rules["Rules"] = list(inventory_rules)
    state["BusinessRules"] = business_rules
    return True
