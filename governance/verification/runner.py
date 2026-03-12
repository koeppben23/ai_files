"""Run contract verification and emit completion matrix artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from governance.contracts.registry import load_and_validate_contracts
from governance.verification.completion_matrix import is_merge_allowed
from governance.verification.pipeline import run_verifier_pipeline


def _load_verification_registry(repo_root: Path) -> dict[str, object]:
    path = repo_root / "governance" / "contracts" / "verification_registry.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification registry root must be object")
    return payload


def _run_pytest_node(python_bin: str, repo_root: Path, nodeid: str) -> bool:
    command = [python_bin, "-m", "pytest", "-q", nodeid]
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode == 0


def _static_status(contract: Mapping[str, object], repo_root: Path) -> str:
    hotspots = contract.get("code_hotspots")
    if not isinstance(hotspots, list) or not hotspots:
        return "FAIL"
    for hotspot in hotspots:
        path = repo_root / str(hotspot)
        if not path.exists():
            return "FAIL"
    return "PASS"


def _method_status(
    *,
    method: str,
    contract: Mapping[str, object],
    registry: Mapping[str, object],
    python_bin: str,
    repo_root: Path,
    cache: dict[str, bool],
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
            cache[node] = _run_pytest_node(python_bin, repo_root, node)
        if not cache[node]:
            return "FAIL"
    return "PASS"


def run_contract_verification(*, repo_root: Path, python_bin: str = sys.executable) -> dict[str, object]:
    try:
        loaded = load_and_validate_contracts(repo_root)
    except Exception as exc:
        return {
            "status": "FAIL",
            "reason": "contract_load_failed",
            "errors": [str(exc)],
        }
    if not loaded.validation.ok:
        return {
            "status": "FAIL",
            "reason": "contract_validation_failed",
            "errors": list(loaded.validation.errors),
        }
    try:
        registry = _load_verification_registry(repo_root)
    except Exception as exc:
        return {
            "status": "FAIL",
            "reason": "verification_registry_load_failed",
            "errors": [str(exc)],
        }
    cache: dict[str, bool] = {}

    static_results: dict[str, str] = {}
    behavioral_results: dict[str, str] = {}
    user_surface_results: dict[str, str] = {}
    live_flow_results: dict[str, str] = {}
    receipts_results: dict[str, str] = {}

    for contract in loaded.contracts:
        req_id = str(contract.get("id") or "").strip()
        static_results[req_id] = _static_status(contract, repo_root)
        behavioral_results[req_id] = _method_status(
            method="behavioral_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
        )
        user_surface_results[req_id] = _method_status(
            method="user_surface_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
        )
        live_flow_results[req_id] = _method_status(
            method="live_flow_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
        )
        receipts_results[req_id] = _method_status(
            method="receipts_verification",
            contract=contract,
            registry=registry,
            python_bin=python_bin,
            repo_root=repo_root,
            cache=cache,
        )

    verifier_result = run_verifier_pipeline(
        requirements=loaded.contracts,
        static_results=static_results,
        behavioral_results=behavioral_results,
        user_surface_results=user_surface_results,
        live_flow_results=live_flow_results,
        receipts_results=receipts_results,
    )
    matrix_payload = verifier_result.matrix.to_dict()
    merge_allowed, reason = is_merge_allowed(matrix_payload)
    status = "PASS" if merge_allowed else "FAIL"
    return {
        "status": status,
        "merge_allowed": merge_allowed,
        "merge_reason": reason,
        "matrix": matrix_payload,
    }
