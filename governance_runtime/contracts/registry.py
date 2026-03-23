"""Requirement contract discovery and loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from governance_runtime.contracts.validator import ContractValidationResult, validate_requirement_contracts


@dataclass(frozen=True)
class LoadedContracts:
    contracts: tuple[dict[str, object], ...]
    validation: ContractValidationResult


def discover_requirement_contract_files(root: Path) -> tuple[Path, ...]:
    base = root / "governance_runtime" / "contracts" / "requirements"
    if not base.exists():
        return ()
    files = sorted([path for path in base.glob("*.json") if path.is_file()])
    return tuple(files)


def load_and_validate_contracts(root: Path) -> LoadedContracts:
    files = discover_requirement_contract_files(root)
    contracts: list[dict[str, object]] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            contracts.append(payload)
    validation = validate_requirement_contracts(contracts)
    return LoadedContracts(contracts=tuple(contracts), validation=validation)
