#!/usr/bin/env python3
"""Run governance contract verification and enforce merge gate policy."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run governance contract verification")
    parser.add_argument("--repo-root", default=".", help="Repository root path")
    parser.add_argument("--out", default="artifacts/governance_completion_matrix.json", help="Output JSON file")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    run = subprocess.run(
        [sys.executable, "-m", "governance_runtime.entrypoints.verify_contracts", "--quiet"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    payload: dict[str, object] = {}
    try:
        payload = json.loads((run.stdout or "{}").strip() or "{}")
    except Exception:
        payload = {}
    status = str(payload.get("status") or "error").lower()
    result = {
        "status": "PASS" if status == "ok" else "FAIL",
        "merge_allowed": status == "ok",
        "merge_reason": str(payload.get("merge_reason") or payload.get("message") or "verification failed"),
        "matrix": {
            "overall_status": str(payload.get("overall_status") or ("PASS" if status == "ok" else "FAIL")),
            "completion_matrix": [],
            "release_blocking_requirements_failed": [],
            "release_blocking_requirements_unverified": [],
        },
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=True))
    return 0 if str(result.get("status")) == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
