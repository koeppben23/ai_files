from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple, cast
import hashlib
import os
import re
import subprocess

from governance_runtime.application.use_cases.bootstrap_session import evaluate_bootstrap_identity
from governance_runtime.engine.adapters import LocalHostAdapter
from governance_runtime.infrastructure.path_contract import normalize_absolute_path, normalize_for_fingerprint
from governance_runtime.infrastructure.wiring import configure_gateway_registry

try:
    from governance_runtime.infrastructure.adapters.git.git_cli import GitCliClient
except Exception:
    GitCliClient = None


@dataclass(frozen=True)
class RepoIdentity:
    root: Path
    fingerprint: str
    name: str
    source: str


class _RepoIdentityAdapter(LocalHostAdapter):
    def __init__(self, repo_root: Path):
        super().__init__()
        resolved = normalize_absolute_path(str(repo_root), purpose="repo_root")
        self._repo_root = resolved
        env = dict(os.environ)
        env["OPENCODE_REPO_ROOT"] = str(resolved)
        self._env = env

    def environment(self):
        return self._env

    def cwd(self) -> Path:
        return self._repo_root


def _is_canonical_fingerprint(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{24}", value.strip()))


def derive_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
    if start_path is None:
        start_path = Path.cwd()
    
    # Try GitCliClient first if available
    if GitCliClient is not None:
        git_client = GitCliClient()
        root = git_client.resolve_repo_root(start_path)
        if root:
            try:
                return normalize_absolute_path(str(root), purpose="repo_root")
            except Exception:
                return None
        return None
    
    # Fallback to subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start_path),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    if not root:
        return None
    try:
        return normalize_absolute_path(root, purpose="repo_root")
    except Exception:
        return None


def derive_fingerprint(repo_root: Path) -> str:
    normalized_repo_root = normalize_absolute_path(str(repo_root), purpose="repo_root")
    try:
        configure_gateway_registry()
        identity = evaluate_bootstrap_identity(adapter=cast(Any, _RepoIdentityAdapter(normalized_repo_root)))
        fp = (identity.repo_fingerprint or "").strip()
        if _is_canonical_fingerprint(fp):
            return fp
    except Exception:
        pass

    normalized_root = normalize_for_fingerprint(normalized_repo_root)
    material = f"repo:local:{normalized_root}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def derive_repo_name(repo_root: Path) -> str:
    return repo_root.name


def derive_repo_identity(start_path: Optional[Path] = None) -> Optional[RepoIdentity]:
    root = derive_repo_root(start_path)
    if root is None:
        return None
    return RepoIdentity(
        root=root,
        fingerprint=derive_fingerprint(root),
        name=derive_repo_name(root),
        source="git-metadata",
    )


def resolve_repo_root_ssot(explicit_root: Optional[Path] = None) -> Tuple[Optional[Path], str]:
    if explicit_root is not None:
        try:
            return normalize_absolute_path(str(explicit_root), purpose="explicit_repo_root"), "explicit"
        except Exception:
            return None, "invalid-explicit"

    env_root = os.environ.get("OPENCODE_REPO_ROOT", "").strip()
    if env_root:
        try:
            return normalize_absolute_path(env_root, purpose="OPENCODE_REPO_ROOT"), "env"
        except Exception:
            pass

    root = derive_repo_root(Path.cwd())
    if root is not None:
        return root, "git-metadata"
    return None, "not-a-git-repo"
