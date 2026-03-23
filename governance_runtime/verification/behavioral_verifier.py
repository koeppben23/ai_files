"""D2 behavioral verification for requirement tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping


def _method_status(
    *,
    method: str,
    contract: Mapping[str, object],
    registry: Mapping[str, object],
    python_bin: str,
    repo_root: Path,
    cache: dict[str, bool],
    run_pytest_node: Callable[[str, Path, str], bool],
) -> str:
    required_methods = contract.get("verification_methods")
    required = set(required_methods) if isinstance(required_methods, list) else set()
    if method not in required:
        return "PASS"

    req_id = str(contract.get("id") or "").strip()
    requirements = registry.get("requirements")
    req_cfg = requirements.get(req_id) if isinstance(requirements, dict) else None
    tests = req_cfg.get(method) if isinstance(req_cfg, dict) else None
    if not isinstance(tests, list) or not tests:
        return "UNVERIFIED"

    for nodeid in tests:
        node = str(nodeid).strip()
        if not node:
            return "FAIL"
        if node not in cache:
            cache[node] = run_pytest_node(python_bin, repo_root, node)
        if not cache[node]:
            return "FAIL"
    return "PASS"


def run_behavioral_verification(
    *,
    requirements: tuple[Mapping[str, object], ...],
    registry: Mapping[str, object],
    python_bin: str,
    repo_root: Path,
    cache: dict[str, bool],
    run_pytest_node: Callable[[str, Path, str], bool],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for contract in requirements:
        req_id = str(contract.get("id") or "").strip()
        out[req_id] = _method_status(
            method="behavioral_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
            run_pytest_node=run_pytest_node,
        )
    return out


def run_user_surface_verification(
    *,
    requirements: tuple[Mapping[str, object], ...],
    registry: Mapping[str, object],
    python_bin: str,
    repo_root: Path,
    cache: dict[str, bool],
    run_pytest_node: Callable[[str, Path, str], bool],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for contract in requirements:
        req_id = str(contract.get("id") or "").strip()
        out[req_id] = _method_status(
            method="user_surface_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
            run_pytest_node=run_pytest_node,
        )
    return out


def run_live_flow_verification(
    *,
    requirements: tuple[Mapping[str, object], ...],
    registry: Mapping[str, object],
    python_bin: str,
    repo_root: Path,
    cache: dict[str, bool],
    run_pytest_node: Callable[[str, Path, str], bool],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for contract in requirements:
        req_id = str(contract.get("id") or "").strip()
        out[req_id] = _method_status(
            method="live_flow_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
            run_pytest_node=run_pytest_node,
        )
    return out


def run_receipts_verification(
    *,
    requirements: tuple[Mapping[str, object], ...],
    registry: Mapping[str, object],
    python_bin: str,
    repo_root: Path,
    cache: dict[str, bool],
    run_pytest_node: Callable[[str, Path, str], bool],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for contract in requirements:
        req_id = str(contract.get("id") or "").strip()
        out[req_id] = _method_status(
            method="receipts_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
            run_pytest_node=run_pytest_node,
        )
    return out
