#!/usr/bin/env python3
"""Audit Bundle CLI - Export and verify governance evidence bundles.

Evidence bundles are CRITICAL for audit and reproducibility.
They allow offline verification of governance decisions.

Usage:
    python scripts/audit_bundle.py --export --run <run_id> --out bundle.zip
    python scripts/audit_bundle.py --verify --bundle bundle.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _find_workspaces_home() -> Path:
    """Find workspaces home directory."""
    import os
    config_root = os.environ.get("OPENCODE_CONFIG_ROOT", "")
    if config_root:
        return Path(config_root) / "workspaces"
    return Path.home() / ".config" / "opencode" / "workspaces"


def _compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _load_run_summary(path: Path) -> dict[str, Any] | None:
    """Load a run summary from file."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _find_run_path(workspaces_home: Path, run_id: str) -> Path | None:
    """Find a run summary path by ID."""
    matches = list(workspaces_home.glob(f"*/evidence/runs/{run_id}.json"))
    if matches:
        return matches[0]
    return None


def export_bundle(
    workspaces_home: Path,
    run_id: str,
    output_path: Path,
) -> tuple[bool, str]:
    """Export an evidence bundle for a run.
    
    The bundle includes:
    - Run summary
    - Evidence pointers (session state, repo cache, etc.)
    - SHA256 manifest for verification
    
    Returns:
        (success, message)
    """
    run_path = _find_run_path(workspaces_home, run_id)
    if not run_path:
        return False, f"Run not found: {run_id}"
    
    run_summary = _load_run_summary(run_path)
    if not run_summary:
        return False, f"Failed to load run summary: {run_path}"
    
    # Collect evidence files
    evidence_files = []
    manifest: dict[str, dict[str, str]] = {}
    
    # Add run summary
    evidence_files.append(("run_summary.json", run_path))
    manifest["run_summary.json"] = {
        "hash": _compute_file_hash(run_path),
        "source": str(run_path),
    }
    
    # Add evidence pointers
    evidence_pointers = run_summary.get("evidence_pointers", {})
    for name, path_str in evidence_pointers.items():
        path = Path(path_str)
        if path.exists():
            target_name = f"evidence/{name}.json"
            evidence_files.append((target_name, path))
            manifest[target_name] = {
                "hash": _compute_file_hash(path),
                "source": str(path),
            }
    
    # Create bundle
    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write manifest
            manifest_data = {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "files": manifest,
            }
            zf.writestr("manifest.json", json.dumps(manifest_data, indent=2, sort_keys=True))
            
            # Write evidence files
            for target_name, source_path in evidence_files:
                zf.write(source_path, target_name)
        
        return True, f"Bundle exported to: {output_path}"
    
    except OSError as e:
        return False, f"Failed to create bundle: {e}"


def verify_bundle(bundle_path: Path) -> tuple[bool, list[str]]:
    """Verify an evidence bundle.
    
    Checks:
    1. Manifest exists and is valid
    2. All files in manifest exist
    3. All hashes match
    
    Returns:
        (valid, list of issues)
    """
    issues = []
    
    if not bundle_path.exists():
        return False, [f"Bundle not found: {bundle_path}"]
    
    try:
        with zipfile.ZipFile(bundle_path, "r") as zf:
            # Check manifest
            if "manifest.json" not in zf.namelist():
                return False, ["Missing manifest.json"]
            
            manifest_data = json.loads(zf.read("manifest.json"))
            
            # Verify version
            if manifest_data.get("version") != "1.0":
                issues.append(f"Unknown manifest version: {manifest_data.get('version')}")
            
            # Verify each file
            files = manifest_data.get("files", {})
            for target_name, file_info in files.items():
                if target_name not in zf.namelist():
                    issues.append(f"Missing file in bundle: {target_name}")
                    continue
                
                # Verify hash
                expected_hash = file_info.get("hash", "")
                actual_hash = hashlib.sha256(zf.read(target_name)).hexdigest()
                
                if expected_hash and actual_hash != expected_hash:
                    issues.append(f"Hash mismatch for {target_name}")
                    issues.append(f"  Expected: {expected_hash}")
                    issues.append(f"  Actual:   {actual_hash}")
    
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as e:
        return False, [f"Failed to read bundle: {e}"]
    
    return len(issues) == 0, issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Bundle CLI - Export and verify governance evidence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --export --run abc123 --out bundle.zip
  %(prog)s --verify --bundle bundle.zip
        """,
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--export",
        action="store_true",
        help="Export an evidence bundle for a run",
    )
    group.add_argument(
        "--verify",
        action="store_true",
        help="Verify an evidence bundle",
    )
    
    parser.add_argument(
        "--run",
        metavar="RUN_ID",
        help="Run ID to export",
    )
    
    parser.add_argument(
        "--out",
        metavar="PATH",
        type=Path,
        help="Output path for bundle (default: bundle_<run_id>.zip)",
    )
    
    parser.add_argument(
        "--bundle",
        metavar="PATH",
        type=Path,
        help="Path to bundle to verify",
    )
    
    args = parser.parse_args()
    
    workspaces_home = _find_workspaces_home()
    
    if args.export:
        if not args.run:
            print("Error: --run is required for export", file=sys.stderr)
            return 1
        
        output_path = args.out
        if not output_path:
            output_path = Path(f"bundle_{args.run}.zip")
        
        success, message = export_bundle(workspaces_home, args.run, output_path)
        print(message)
        return 0 if success else 1
    
    if args.verify:
        if not args.bundle:
            print("Error: --bundle is required for verify", file=sys.stderr)
            return 1
        
        valid, issues = verify_bundle(args.bundle)
        
        if valid:
            print(f"✓ Bundle verified: {args.bundle}")
            return 0
        else:
            print(f"✗ Bundle verification failed:")
            for issue in issues:
                print(f"  {issue}")
            return 1
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
