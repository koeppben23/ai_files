from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepoIdentity:
    repo_root: str
    fingerprint: str
    repo_name: str
    source: str
