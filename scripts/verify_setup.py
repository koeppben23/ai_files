#!/usr/bin/env python3
"""Verify governance installation and configuration.

Usage:
    python3 scripts/verify_setup.py

Checks:
- Installation status
- Binding file presence and validity
- Required commands in PATH
- Profile detection
- Workspace directory structure
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def check_command(cmd: str) -> tuple[bool, str]:
    """Check if a command is available in PATH."""
    try:
        result = subprocess.run(
            ["which", cmd] if sys.platform != "win32" else ["where", cmd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.strip().split("\n")[0]
        return False, "not found"
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)


def check_binding_file() -> tuple[bool, str, dict[str, Any] | None]:
    """Check if binding file exists and is valid."""
    home = Path.home()
    config_root = home / ".config" / "opencode"
    binding_file = config_root / "commands" / "governance.paths.json"
    
    if not binding_file.exists():
        return False, "not found", None
    
    try:
        with open(binding_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        required_keys = {"configRoot", "commandsHome", "profilesHome"}
        paths = data.get("paths", {})
        if not required_keys.issubset(paths.keys()):
            missing = required_keys - paths.keys()
            return False, f"missing keys: {missing}", data
        
        flat_data = {
            "user_home": str(home),
            "config_root": paths.get("configRoot", ""),
            "commands_home": paths.get("commandsHome", ""),
            "profiles_home": paths.get("profilesHome", ""),
            "workspaces_home": paths.get("workspacesHome", ""),
        }
        
        return True, "valid", flat_data
    except json.JSONDecodeError as e:
        return False, f"invalid JSON: {e}", None


def check_workspace_dir() -> tuple[bool, str]:
    """Check if workspace directory exists."""
    home = Path.home()
    config_root = home / ".config" / "opencode"
    workspaces_dir = config_root / "workspaces"
    
    if not workspaces_dir.exists():
        return True, "will be created on first run"
    
    return True, f"exists at {workspaces_dir}"


def detect_profile() -> str:
    """Detect likely profile based on repo signals."""
    cwd = Path.cwd()
    
    signals = {
        "backend-python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
        "backend-java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "frontend-angular-nx": ["angular.json", "nx.json"],
    }
    
    for profile, files in signals.items():
        for f in files:
            if (cwd / f).exists():
                return profile
    
    return "fallback-minimum"


def run_verification() -> dict[str, Any]:
    """Run all verification checks."""
    results = {
        "overall": True,
        "checks": [],
    }
    
    checks = [
        ("Python version", lambda: (True, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")),
        ("Git available", lambda: check_command("git")),
        ("Binding file", lambda: check_binding_file()[:2]),
        ("Workspace directory", lambda: check_workspace_dir()),
    ]
    
    for name, check_fn in checks:
        try:
            passed, message = check_fn()
        except Exception as e:
            passed, message = False, str(e)
        
        results["checks"].append({
            "name": name,
            "passed": passed,
            "message": message,
        })
        
        if not passed:
            results["overall"] = False
    
    _, _, binding_data = check_binding_file()
    results["binding_data"] = binding_data
    results["detected_profile"] = detect_profile()
    
    return results


def print_report(results: dict[str, Any]) -> None:
    """Print verification report."""
    print("=" * 60)
    print("GOVERNANCE VERIFICATION REPORT")
    print("=" * 60)
    print()
    
    for check in results["checks"]:
        status = "✓" if check["passed"] else "✗"
        print(f"  {status} {check['name']}: {check['message']}")
    
    print()
    
    if results.get("binding_data"):
        print("-" * 60)
        print("BINDING CONFIGURATION")
        print("-" * 60)
        for key, value in results["binding_data"].items():
            print(f"  {key}: {value}")
        print()
    
    print("-" * 60)
    print("DETECTED PROFILE")
    print("-" * 60)
    print(f"  {results['detected_profile']}")
    print()
    
    print("=" * 60)
    if results["overall"]:
        print("STATUS: ✓ READY")
        print()
        print("Next steps:")
        print("  1. Run /start in OpenCode to begin a governance session")
        print("  2. Provide a task description")
        print("  3. Say 'Implement now' to proceed with implementation")
    else:
        print("STATUS: ✗ SETUP REQUIRED")
        print()
        print("Fix the issues above, then run this script again.")
    print("=" * 60)


def main() -> int:
    results = run_verification()
    print_report(results)
    return 0 if results["overall"] else 1


if __name__ == "__main__":
    sys.exit(main())
