#!/usr/bin/env python3
"""Audit CLI - Explain governance runs deterministically.

Usage:
    python scripts/audit_explain.py --last
    python scripts/audit_explain.py --run <run_id>
    python scripts/audit_explain.py --list --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _find_workspaces_home() -> Path:
    """Find workspaces home directory."""
    import os
    config_root = os.environ.get("OPENCODE_CONFIG_ROOT", "")
    if config_root:
        return Path(config_root) / "workspaces"
    return Path.home() / ".config" / "opencode" / "workspaces"


def _load_run_summary(path: Path) -> dict[str, Any] | None:
    """Load a run summary from file."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        return ts


def explain_run(summary: dict[str, Any]) -> str:
    """Generate human-readable explanation of a run."""
    lines = []
    
    lines.append("=" * 60)
    lines.append("GOVERNANCE RUN SUMMARY")
    lines.append("=" * 60)
    lines.append("")
    
    lines.append(f"Run ID:     {summary.get('run_id', 'unknown')}")
    lines.append(f"Timestamp:  {_format_timestamp(summary.get('timestamp', 'unknown'))}")
    lines.append(f"Mode:       {summary.get('mode', 'unknown')}")
    lines.append(f"Phase:      {summary.get('phase', 'unknown')}")
    lines.append(f"Result:     {summary.get('result', 'unknown')}")
    lines.append("")
    
    reason = summary.get("reason", {})
    reason_code = reason.get("code", "UNKNOWN")
    
    if reason_code and reason_code != "OK":
        lines.append("-" * 60)
        lines.append("BLOCKED REASON")
        lines.append("-" * 60)
        lines.append(f"Code:       {reason_code}")
        
        if "message" in reason:
            lines.append(f"Message:    {reason['message']}")
        
        if "how_to_fix" in reason:
            lines.append("")
            lines.append("HOW TO FIX:")
            lines.append(reason["how_to_fix"])
        
        if "payload" in reason:
            lines.append("")
            lines.append("PAYLOAD:")
            for key, value in reason["payload"].items():
                lines.append(f"  {key}: {value}")
        
        lines.append("")
    
    precedence_events = summary.get("precedence_events", [])
    if precedence_events:
        lines.append("-" * 60)
        lines.append("PRECEDENCE EVENTS")
        lines.append("-" * 60)
        for event in precedence_events:
            lines.append(f"  {event.get('event', 'unknown')}")
            lines.append(f"    Source: {event.get('source', 'unknown')}")
        lines.append("")
    
    prompt_budget = summary.get("prompt_budget", {})
    if prompt_budget.get("used") is not None:
        lines.append("-" * 60)
        lines.append("PROMPT BUDGET")
        lines.append("-" * 60)
        lines.append(f"  Used:    {prompt_budget.get('used', 0)}")
        lines.append(f"  Allowed: {prompt_budget.get('allowed', 100)}")
        lines.append("")
    
    evidence_pointers = summary.get("evidence_pointers", {})
    if evidence_pointers:
        lines.append("-" * 60)
        lines.append("EVIDENCE POINTERS")
        lines.append("-" * 60)
        for key, path in evidence_pointers.items():
            lines.append(f"  {key}: {path}")
        lines.append("")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)


def find_latest_run(workspaces_home: Path) -> Path | None:
    """Find the latest run summary."""
    if not workspaces_home.exists():
        return None
    
    latest_links = list(workspaces_home.glob("*/evidence/runs/latest.json"))
    if not latest_links:
        return None
    
    return latest_links[0].resolve()


def list_runs(workspaces_home: Path, limit: int = 20) -> list[dict[str, Any]]:
    """List recent runs."""
    if not workspaces_home.exists():
        return []
    
    runs = []
    run_files = list(workspaces_home.glob("*/evidence/runs/*.json"))
    run_files = [f for f in run_files if f.name != "latest.json"]
    
    run_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    
    for run_file in run_files[:limit]:
        summary = _load_run_summary(run_file)
        if summary:
            runs.append(summary)
    
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit CLI - Explain governance runs deterministically",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --last                    Explain the most recent run
  %(prog)s --run abc123              Explain a specific run
  %(prog)s --list --limit 10         List last 10 runs
        """,
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--last",
        action="store_true",
        help="Explain the most recent run",
    )
    group.add_argument(
        "--run",
        metavar="RUN_ID",
        help="Explain a specific run by ID",
    )
    group.add_argument(
        "--list",
        action="store_true",
        help="List recent runs",
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of runs to list (default: 20)",
    )
    
    args = parser.parse_args()
    
    workspaces_home = _find_workspaces_home()
    
    if args.list:
        runs = list_runs(workspaces_home, args.limit)
        if not runs:
            print("No runs found.", file=sys.stderr)
            return 1
        
        print(f"{'TIMESTAMP':<22} {'MODE':<10} {'PHASE':<6} {'RESULT':<10} {'REASON'}")
        print("-" * 70)
        for run in runs:
            ts = _format_timestamp(run.get("timestamp", "unknown"))
            mode = run.get("mode", "unknown")
            phase = run.get("phase", "?")
            result = run.get("result", "unknown")
            reason_code = run.get("reason", {}).get("code", "")
            print(f"{ts:<22} {mode:<10} {phase:<6} {result:<10} {reason_code}")
        return 0
    
    if args.last:
        run_path = find_latest_run(workspaces_home)
        if not run_path:
            print("No runs found. Run /start to create a governance session.", file=sys.stderr)
            return 1
    else:
        run_path = workspaces_home / "*/evidence/runs" / f"{args.run}.json"
        matches = list(workspaces_home.glob(f"*/evidence/runs/{args.run}.json"))
        if not matches:
            print(f"Run not found: {args.run}", file=sys.stderr)
            return 1
        run_path = matches[0]
    
    summary = _load_run_summary(run_path)
    if not summary:
        print(f"Failed to load run summary: {run_path}", file=sys.stderr)
        return 1
    
    print(explain_run(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
