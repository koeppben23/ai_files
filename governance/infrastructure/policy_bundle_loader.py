"""Loader for policy-bound diagnostics config bundle.

Fail-closed loader for kernel policy configs:
- bootstrap_policy.yaml
- persistence_artifacts.yaml
- blocked_reason_catalog.yaml
- phase_execution_config.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.path_contract import normalize_absolute_path, PathContractError


class PolicyBundleError(RuntimeError):
    pass


_POLICY_FILES = (
    "bootstrap_policy.yaml",
    "persistence_artifacts.yaml",
    "blocked_reason_catalog.yaml",
    "phase_execution_config.yaml",
)


def _repo_local_diagnostics_root() -> Path:
    parts = Path(__file__).parts
    if "governance" in parts:
        i = parts.index("governance")
        repo_root = Path(*parts[:i])
        return repo_root / "diagnostics"
    return Path(__file__).parent.parent.parent / "diagnostics"


def _resolve_policy_path(filename: str, *, mode: str) -> Path:
    effective_mode = str(mode).strip().lower() or "user"
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode=effective_mode)
    if evidence.binding_ok and evidence.commands_home:
        candidate = evidence.commands_home / "diagnostics" / filename
        if candidate.exists():
            return candidate

    # Runtime canonical fallback for packaged repo diagnostics (deterministic path).
    if effective_mode != "pipeline":
        repo_root = str(os.environ.get("OPENCODE_REPO_ROOT", "")).strip()
        if repo_root:
            try:
                repo_root_path = normalize_absolute_path(repo_root, purpose="env:OPENCODE_REPO_ROOT")
            except PathContractError:
                repo_root_path = None
            if repo_root_path is not None:
                candidate = repo_root_path / "diagnostics" / filename
                if candidate.exists():
                    return candidate

    if effective_mode != "pipeline" and str(os.environ.get("OPENCODE_ALLOW_REPO_LOCAL_CONFIG", "")).strip() == "1":
        candidate = _repo_local_diagnostics_root() / filename
        if candidate.exists():
            return candidate

    raise PolicyBundleError(
        f"Policy config not resolved via canonical root: {filename}. "
        "Reason: BLOCKED-ENGINE-SELFCHECK"
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise PolicyBundleError("YAML parser not available. Reason: BLOCKED-ENGINE-SELFCHECK")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PolicyBundleError(f"Policy config parse failed ({path}): {exc}. Reason: BLOCKED-ENGINE-SELFCHECK")
    if not isinstance(data, dict) or not data:
        raise PolicyBundleError(f"Policy config empty/invalid: {path}. Reason: BLOCKED-ENGINE-SELFCHECK")
    policy = data.get("policy")
    if not isinstance(policy, dict):
        raise PolicyBundleError(f"Policy metadata missing: {path}. Reason: BLOCKED-ENGINE-SELFCHECK")
    if policy.get("pack_locked") is not True:
        raise PolicyBundleError(f"pack_locked must be true: {path}. Reason: BLOCKED-ENGINE-SELFCHECK")
    if policy.get("precedence_level") != "engine_master_policy":
        raise PolicyBundleError(f"precedence_level invalid: {path}. Reason: BLOCKED-ENGINE-SELFCHECK")
    return data


def ensure_policy_bundle_loaded(*, mode: str = "user") -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for filename in _POLICY_FILES:
        path = _resolve_policy_path(filename, mode=mode)
        loaded[filename] = _load_yaml(path)
    return loaded
