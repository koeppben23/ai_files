"""Loader for policy-bound governance config bundle.

Fail-closed loader for kernel policy configs:
- bootstrap_policy.yaml
- persistence_artifacts.yaml
- blocked_reason_catalog.yaml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.path_contract import normalize_absolute_path


class PolicyBundleError(RuntimeError):
    pass


_POLICY_FILES = (
    "bootstrap_policy.yaml",
    "persistence_artifacts.yaml",
    "blocked_reason_catalog.yaml",
)


def _policy_relpath(filename: str) -> Path:
    return Path("governance_runtime/assets/config") / filename


def _resolve_policy_path(filename: str, *, mode: str) -> Path:
    effective_mode = str(mode).strip().lower() or "user"
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode=effective_mode)
    if not evidence.binding_ok or evidence.commands_home is None:
        raise PolicyBundleError(
            f"Policy config not resolved via canonical root: {filename}. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    candidate = evidence.commands_home / _policy_relpath(filename)
    candidate = normalize_absolute_path(str(candidate), purpose=f"policy:{filename}")
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
    except (OSError, ValueError, yaml.YAMLError) as exc:
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
