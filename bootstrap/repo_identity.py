from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import subprocess
import os


@dataclass(frozen=True)
class RepoIdentity:
    root: Path
    fingerprint: str
    name: str
    
    def to_dict(self):
        return {
            "root": str(self.root),
            "fingerprint": self.fingerprint,
            "name": self.name,
        }


def derive_repo_root(start_path: Optional[Path] = None) -> Optional[Path]:
    if start_path is None:
        start_path = Path.cwd()
    
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_path,
            capture_output=True,
            text=True,
            check=True,
        )
        root = result.stdout.strip()
        if root:
            return Path(root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return None


def derive_fingerprint(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        remote_url = result.stdout.strip()
        if remote_url:
            import hashlib
            return hashlib.sha256(remote_url.encode()).hexdigest()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return "unknown"


def derive_repo_name(repo_root: Path) -> str:
    return repo_root.name


def derive_repo_identity(start_path: Optional[Path] = None) -> Optional[RepoIdentity]:
    repo_root = derive_repo_root(start_path)
    if not repo_root:
        return None
    
    fingerprint = derive_fingerprint(repo_root)
    name = derive_repo_name(repo_root)
    
    return RepoIdentity(root=repo_root, fingerprint=fingerprint, name=name)
