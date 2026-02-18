from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit

from governance.infrastructure.path_contract import normalize_for_fingerprint


@dataclass(frozen=True)
class RepoIdentity:
    fingerprint: str
    material_class: Literal["remote_canonical", "local_path"]
    canonical_remote: str | None
    normalized_repo_root: str
    git_dir_path: str | None


def canonicalize_origin_url(remote: str) -> str | None:
    raw = remote.strip()
    if not raw:
        return None
    scp_style = re.match(r"^(?P<user>[^@/\s]+)@(?P<host>[^:/\s]+):(?P<path>[^\s]+)$", raw)
    if scp_style:
        raw = f"ssh://{scp_style.group('user')}@{scp_style.group('host')}/{scp_style.group('path')}"

    try:
        parsed = urlsplit(raw)
    except Exception:
        return None

    if not parsed.scheme or not parsed.netloc:
        return None
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if not host:
        return None
    if parsed.port:
        host = f"{host}:{parsed.port}"

    path = parsed.path.replace("\\", "/")
    path = re.sub(r"/+", "/", path).strip()
    if not path:
        return None
    if not path.startswith("/"):
        path = f"/{path}"
    if path.lower().endswith(".git"):
        path = path[:-4]
    path = path.rstrip("/").casefold()
    if not path:
        return None
    return f"repo://{host}{path}"


def derive_repo_identity(repo_root: Path, *, canonical_remote: str | None, git_dir: Path | None) -> RepoIdentity:
    normalized_root = normalize_for_fingerprint(repo_root)
    if canonical_remote:
        material = f"repo:{canonical_remote}"
        fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
        return RepoIdentity(
            fingerprint=fp,
            material_class="remote_canonical",
            canonical_remote=canonical_remote,
            normalized_repo_root=normalized_root,
            git_dir_path=str(git_dir) if git_dir is not None else None,
        )
    material = f"repo:local:{normalized_root}"
    fp = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return RepoIdentity(
        fingerprint=fp,
        material_class="local_path",
        canonical_remote=None,
        normalized_repo_root=normalized_root,
        git_dir_path=str(git_dir) if git_dir is not None else None,
    )
