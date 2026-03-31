from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence


class GitCliClient:
    """Git CLI adapter - Infrastructure implementation for Git operations.
    
    This adapter encapsulates all Git CLI interactions. It should be used
    through the GitPort protocol in application code.
    """

    def resolve_repo_root(self, cwd: Path | None = None) -> Path | None:
        """Resolve the Git repository root (top-level directory).
        
        Args:
            cwd: Working directory to check. If None, uses current directory.
            
        Returns:
            Path to the repository root, or None if not in a git repo.
        """
        try:
            run = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                text=True,
                capture_output=True,
                check=False,
                cwd=str(cwd) if cwd is not None else None,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            return None
        if run.returncode != 0:
            return None
        value = run.stdout.strip()
        return Path(value) if value else None

    def is_inside_work_tree(self, cwd: Path | None = None) -> bool:
        """Check if the given path is inside a Git working tree.
        
        Args:
            cwd: Path to check. If None, uses current directory.
            
        Returns:
            True if inside a working tree, False otherwise.
        """
        run = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        return run.returncode == 0 and run.stdout.strip().lower() == "true"

    def get_origin_remote(self, cwd: Path | None = None) -> str | None:
        """Get the URL of the 'origin' remote.
        
        Args:
            cwd: Repository directory. If None, uses current directory.
            
        Returns:
            Remote URL string, or None if no origin remote exists.
        """
        run = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        if run.returncode != 0:
            return None
        return run.stdout.strip() or None

    def get_config(
        self,
        key: str,
        cwd: Path | None = None,
        scope: str | None = None,
    ) -> str | None:
        """Get a Git configuration value.
        
        Args:
            key: Configuration key (e.g., 'core.longpaths').
            cwd: Repository directory. If None, uses current directory.
            scope: Config scope ('local', 'global', 'system'). If None, uses local.
            
        Returns:
            Configuration value, or None if not set or error.
        """
        args = ["git", "config"]
        # Map scope names to git flags: local -> --local, global -> --global, system -> --system
        if scope:
            scope_flag_map = {
                "local": "--local",
                "global": "--global",
                "system": "--system",
            }
            flag = scope_flag_map.get(scope.lower())
            if flag:
                args.append(flag)
            else:
                args.append(scope)
        args.extend(["--get", key])
        
        run = subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        if run.returncode != 0:
            return None
        return run.stdout.strip() or None

    def status_porcelain(self, cwd: Path | None = None) -> list[str]:
        """Get git status in porcelain format.
        
        Args:
            cwd: Repository directory. If None, uses current directory.
            
        Returns:
            List of status lines (one per file).
        """
        run = subprocess.run(
            ["git", "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        if run.returncode != 0:
            return []
        return [line.strip() for line in (run.stdout or "").splitlines() if line.strip()]

    def rev_parse(self, args: Sequence[str], cwd: Path | None = None) -> str | None:
        """Execute git rev-parse with given arguments.
        
        Args:
            args: Sequence of git rev-parse arguments.
            cwd: Repository directory. If None, uses current directory.
            
        Returns:
            Output string, or None on error.
        """
        run = subprocess.run(
            ["git", "rev-parse", *args],
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        if run.returncode != 0:
            return None
        return run.stdout.strip() or None

    def merge_base(self, left: str, right: str, cwd: Path | None = None) -> str | None:
        """Find the merge base of two commits.
        
        Args:
            left: First commit (branch, tag, or SHA).
            right: Second commit (branch, tag, or SHA).
            cwd: Repository directory. If None, uses current directory.
            
        Returns:
            Merge base commit SHA, or None if not found.
        """
        run = subprocess.run(
            ["git", "merge-base", left, right],
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        if run.returncode != 0:
            return None
        return run.stdout.strip() or None

    def diff_name_only(
        self,
        left: str,
        right: str | None = None,
        cwd: Path | None = None,
    ) -> list[str]:
        """Get list of files that differ between two commits.
        
        Args:
            left: Left commit.
            right: Right commit. If None, compares left to working tree.
            cwd: Repository directory. If None, uses current directory.
            
        Returns:
            List of file paths that differ.
        """
        args = ["git", "diff", "--name-only"]
        if right:
            args.extend([left, right])
        else:
            args.append(left)
            
        run = subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=10,
        )
        if run.returncode != 0:
            return []
        return [line.strip() for line in (run.stdout or "").splitlines() if line.strip()]

    def ls_remote(
        self,
        remote: str,
        ref: str | None = None,
        cwd: Path | None = None,
    ) -> list[str]:
        """List remote references.
        
        Args:
            remote: Remote name (e.g., 'origin').
            ref: Optional reference to filter (e.g., 'refs/heads/main').
            cwd: Repository directory. If None, uses current directory.
            
        Returns:
            List of reference lines.
        """
        args = ["git", "ls-remote", remote]
        if ref:
            args.append(ref)
            
        run = subprocess.run(
            args,
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=10,
        )
        if run.returncode != 0:
            return []
        return [line.strip() for line in (run.stdout or "").splitlines() if line.strip()]

    def is_safe_directory(self, path: Path | None = None) -> bool:
        """Check if the directory is marked as safe for Git operations.
        
        This checks Git's safe.directory configuration. A directory is considered
        safe if:
        - It is explicitly listed in safe.directory config, OR
        - safe.directory is set to '*' (wildcard), OR
        - Git is not configured to check (e.g., safe.directory check is disabled)
        
        Args:
            path: Directory to check. If None, checks current directory.
            
        Returns:
            True if directory is safe, False otherwise.
        """
        check_path = str(path) if path else ""
        
        # First, check if we have any safe.directory configuration
        run = subprocess.run(
            ["git", "config", "--get-all", "safe.directory"],
            text=True,
            capture_output=True,
            check=False,
            cwd=check_path if check_path else None,
            timeout=5,
        )
        
        if run.returncode != 0:
            # No safe.directory config at all - on modern Git, this is fine
            # (older Git versions might warn)
            return True
            
        configured_dirs = [d.strip() for d in run.stdout.splitlines() if d.strip()]
        
        for configured in configured_dirs:
            # Wildcard means everything is safe
            if configured == "*":
                return True
            # Exact match
            if configured == check_path:
                return True
            # Check if configured path is a prefix (e.g., configured="/repo" matches "/repo/subdir")
            if check_path.startswith(configured.rstrip("/") + "/"):
                return True
                
        # Not found in safe.directory list
        return False

    def get_safe_directories(self, cwd: Path | None = None) -> list[str]:
        """Get list of configured safe directories.
        
        Args:
            cwd: Repository directory. If None, uses global config.
            
        Returns:
            List of safe directory paths.
        """
        run = subprocess.run(
            ["git", "config", "--get-all", "safe.directory"],
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            timeout=5,
        )
        if run.returncode != 0:
            return []
        return [line.strip() for line in (run.stdout or "").splitlines() if line.strip()]


# Backward-compatible alias for existing code using the function
def resolve_repo_root(cwd: Path | None = None) -> Path | None:
    """Backward-compatible wrapper for GitCliClient.resolve_repo_root()."""
    return GitCliClient().resolve_repo_root(cwd)


def is_inside_work_tree(cwd: Path | None = None) -> bool:
    """Backward-compatible wrapper for GitCliClient.is_inside_work_tree()."""
    return GitCliClient().is_inside_work_tree(cwd)


def get_origin_remote(cwd: Path | None = None) -> str | None:
    """Backward-compatible wrapper for GitCliClient.get_origin_remote()."""
    return GitCliClient().get_origin_remote(cwd)


def get_config(key: str, cwd: Path | None = None, scope: str | None = None) -> str | None:
    """Backward-compatible wrapper for GitCliClient.get_config()."""
    return GitCliClient().get_config(key, cwd, scope)


def status_porcelain(cwd: Path | None = None) -> list[str]:
    """Backward-compatible wrapper for GitCliClient.status_porcelain()."""
    return GitCliClient().status_porcelain(cwd)


def rev_parse(args: Sequence[str], cwd: Path | None = None) -> str | None:
    """Backward-compatible wrapper for GitCliClient.rev_parse()."""
    return GitCliClient().rev_parse(args, cwd)


def merge_base(left: str, right: str, cwd: Path | None = None) -> str | None:
    """Backward-compatible wrapper for GitCliClient.merge_base()."""
    return GitCliClient().merge_base(left, right, cwd)


def diff_name_only(left: str, right: str | None = None, cwd: Path | None = None) -> list[str]:
    """Backward-compatible wrapper for GitCliClient.diff_name_only()."""
    return GitCliClient().diff_name_only(left, right, cwd)


def ls_remote(remote: str, ref: str | None = None, cwd: Path | None = None) -> list[str]:
    """Backward-compatible wrapper for GitCliClient.ls_remote()."""
    return GitCliClient().ls_remote(remote, ref, cwd)


def is_safe_directory(path: Path | None = None) -> bool:
    """Backward-compatible wrapper for GitCliClient.is_safe_directory()."""
    return GitCliClient().is_safe_directory(path)


def get_safe_directories(cwd: Path | None = None) -> list[str]:
    """Backward-compatible wrapper for GitCliClient.get_safe_directories()."""
    return GitCliClient().get_safe_directories(cwd)
