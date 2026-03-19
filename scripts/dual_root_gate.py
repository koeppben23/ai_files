#!/usr/bin/env python3
"""Fail-closed dual-root contract gate.

Validates the installer contract for split roots:
- config root owns commands/workspaces/bindings only
- local root owns runtime/content/spec payload
- canonical rail command surface is exactly the 8 expected commands
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from governance_runtime.engine.command_surface import CANONICAL_COMMANDS
from governance_runtime.install.install import GOVERNANCE_PATHS_NAME, MANIFEST_NAME, build_governance_paths_payload


EXPECTED_RAILS: set[str] = {
    "audit-readout.md",
    "continue.md",
    "implement.md",
    "implementation-decision.md",
    "plan.md",
    "review-decision.md",
    "review.md",
    "ticket.md",
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dual-root installer invariants")
    parser.add_argument("--config-root", default=os.environ.get("OPENCODE_CONFIG_ROOT", str(Path.home() / ".config" / "opencode")))
    parser.add_argument("--local-root", default=os.environ.get("OPENCODE_LOCAL_ROOT", str(Path.home() / ".local" / "opencode")))
    parser.add_argument("--write-report", default="", help="Optional JSON report path")
    return parser.parse_args(argv)


def _check_command_surface() -> list[str]:
    errors: list[str] = []
    canonical = {str(x) for x in CANONICAL_COMMANDS}
    if canonical != EXPECTED_RAILS:
        missing = sorted(EXPECTED_RAILS - canonical)
        extra = sorted(canonical - EXPECTED_RAILS)
        if missing:
            errors.append(f"canonical commands missing: {missing}")
        if extra:
            errors.append(f"canonical commands unexpected: {extra}")
    return errors


def _check_paths_payload(config_root: Path, local_root: Path) -> tuple[list[str], dict]:
    payload = build_governance_paths_payload(config_root=config_root, local_root=local_root, deterministic=True)
    paths = payload.get("paths", {}) if isinstance(payload, dict) else {}
    errors: list[str] = []

    required = {
        "configRoot",
        "localRoot",
        "commandsHome",
        "profilesHome",
        "governanceHome",
        "runtimeHome",
        "contentHome",
        "specHome",
        "workspacesHome",
        "pythonCommand",
    }
    missing = sorted(required - set(paths.keys())) if isinstance(paths, dict) else sorted(required)
    if missing:
        errors.append(f"paths payload missing keys: {missing}")
        return errors, payload

    def p(key: str) -> Path:
        return Path(str(paths[key]))

    if p("commandsHome") != config_root / "commands":
        errors.append("paths.commandsHome must equal configRoot/commands")
    if p("workspacesHome") != config_root / "workspaces":
        errors.append("paths.workspacesHome must equal configRoot/workspaces")
    if p("runtimeHome") != local_root / "governance_runtime":
        errors.append("paths.runtimeHome must equal localRoot/governance_runtime")
    if p("governanceHome") != local_root / "governance":
        errors.append("paths.governanceHome must equal localRoot/governance")
    if p("contentHome") != local_root / "governance_content":
        errors.append("paths.contentHome must equal localRoot/governance_content")
    if p("specHome") != local_root / "governance_spec":
        errors.append("paths.specHome must equal localRoot/governance_spec")
    if p("profilesHome") != p("contentHome") / "profiles":
        errors.append("paths.profilesHome must equal contentHome/profiles")

    return errors, payload


def _check_config_allowlist_contract() -> list[str]:
    allowed = set(EXPECTED_RAILS) | {GOVERNANCE_PATHS_NAME, MANIFEST_NAME}
    errors: list[str] = []
    if len(allowed) != 10:
        errors.append(f"commands allowlist cardinality mismatch: expected 10, got {len(allowed)}")
    if any("/" in name or "\\" in name for name in allowed):
        errors.append("commands allowlist must contain only command-root filenames (no subpaths)")
    return errors


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    config_root = Path(args.config_root).expanduser().resolve()
    local_root = Path(args.local_root).expanduser().resolve()

    issues: list[str] = []
    issues.extend(_check_command_surface())
    path_issues, payload = _check_paths_payload(config_root, local_root)
    issues.extend(path_issues)
    issues.extend(_check_config_allowlist_contract())

    report = {
        "ok": len(issues) == 0,
        "issues": issues,
        "configRoot": str(config_root),
        "localRoot": str(local_root),
        "payloadPreview": payload,
    }

    if args.write_report:
        out = Path(args.write_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if issues:
        print("❌ Dual-root gate failed")
        for issue in issues:
            print(f" - {issue}")
        return 1

    print("✅ Dual-root gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
