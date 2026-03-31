"""Run contract verification and emit completion matrix artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from governance_runtime.contracts.registry import load_and_validate_contracts
from governance_runtime.verification.behavioral_verifier import (
    run_behavioral_verification,
    run_receipts_verification,
    run_user_surface_verification,
)
from governance_runtime.verification.completion_matrix import is_merge_allowed
from governance_runtime.verification.live_flow_verifier import run_live_flow_verification
from governance_runtime.verification.pipeline import run_verifier_pipeline
from governance_runtime.verification.static_verifier import run_static_verification

try:
    from governance_runtime.infrastructure.adapters.process.subprocess_runner import SubprocessRunner
except Exception:
    # import fallback: use direct subprocess if SubprocessRunner unavailable
    SubprocessRunner = None  # pragma: no cover


def _load_verification_registry(repo_root: Path) -> dict[str, object]:
    path = repo_root / "governance_runtime" / "contracts" / "verification_registry.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verification registry root must be object")
    return payload


def _run_pytest_node(python_bin: str, repo_root: Path, nodeid: str) -> bool:
    command = [python_bin, "-m", "pytest", "-q", nodeid]
    
    # Try SubprocessRunner first if available
    if SubprocessRunner is not None:
        runner = SubprocessRunner()
        result = runner.run(command, cwd=repo_root)
        return result.returncode == 0
    
    # Fallback to subprocess
    completed = subprocess.run(
        command,
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode == 0


def _run_node(python_bin: str, repo_root: Path, nodeid: str) -> bool:
    return _run_pytest_node(python_bin, repo_root, nodeid)


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

    static_results = run_static_verification(requirements=loaded.contracts, repo_root=repo_root)
    behavioral_results = run_behavioral_verification(
        requirements=loaded.contracts,
        registry=registry,
        python_bin=python_bin,
        repo_root=repo_root,
        cache=cache,
        run_pytest_node=_run_node,
    )
    user_surface_results = run_user_surface_verification(
        requirements=loaded.contracts,
        registry=registry,
        python_bin=python_bin,
        repo_root=repo_root,
        cache=cache,
        run_pytest_node=_run_node,
    )
    live_flow_results = run_live_flow_verification(
        requirements=loaded.contracts,
        registry=registry,
        python_bin=python_bin,
        repo_root=repo_root,
        cache=cache,
        run_pytest_node=_run_node,
    )
    receipts_results = run_receipts_verification(
        requirements=loaded.contracts,
        registry=registry,
        python_bin=python_bin,
        repo_root=repo_root,
        cache=cache,
        run_pytest_node=_run_node,
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
    status = str(matrix_payload.get("overall_status") or ("PASS" if merge_allowed else "FAIL")).upper()
    return {
        "status": status,
        "merge_allowed": merge_allowed,
        "merge_reason": reason,
        "matrix": matrix_payload,
    }
