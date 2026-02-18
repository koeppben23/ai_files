#!/usr/bin/env python3
"""Validate and scaffold standardized governance workflow templates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


CATALOG_SCHEMA = "governance.workflow-template-catalog.v1"
CATALOG_PATH = Path("templates/github-actions/template_catalog.json")
WORKFLOW_DIR = Path("templates/github-actions")
TEMPLATE_PATTERN = "governance-*.yml"
TEMPLATE_KEY_RE = re.compile(r"^governance-[a-z0-9][a-z0-9-]*$")
ALLOWED_ARCHETYPES = {
    "pr_gate_shadow_live_verify",
    "pipeline_roles_hardened",
    "ruleset_release",
    "golden_output_stability",
    "golden_baseline_update",
}


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _validate_relative_path(raw: str, *, field_name: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative: {raw}")
    if ".." in path.parts:
        raise ValueError(f"{field_name} must not contain path traversal: {raw}")
    return path


def _load_catalog(repo_root: Path, catalog_rel: Path) -> tuple[Path, dict[str, object], list[dict[str, str]]]:
    catalog_path = repo_root / catalog_rel
    payload = _read_json(catalog_path)
    schema = payload.get("schema")
    if schema != CATALOG_SCHEMA:
        raise ValueError(
            f"{catalog_rel}: expected schema={CATALOG_SCHEMA}, found {schema!r}"
        )

    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list) or not raw_templates:
        raise ValueError(f"{catalog_rel}: templates must be a non-empty list")

    normalized: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seen_files: set[str] = set()
    for idx, raw in enumerate(raw_templates, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"{catalog_rel}: templates[{idx}] must be an object")

        missing = [name for name in ("template_key", "file", "archetype", "purpose") if name not in raw]
        if missing:
            raise ValueError(f"{catalog_rel}: templates[{idx}] missing fields {missing}")

        template_key = str(raw["template_key"])
        file_rel = str(raw["file"])
        archetype = str(raw["archetype"])
        purpose = str(raw["purpose"])

        if not TEMPLATE_KEY_RE.fullmatch(template_key):
            raise ValueError(f"{catalog_rel}: invalid template_key '{template_key}'")
        if archetype not in ALLOWED_ARCHETYPES:
            raise ValueError(f"{catalog_rel}: unsupported archetype '{archetype}' for {template_key}")
        if not purpose.strip():
            raise ValueError(f"{catalog_rel}: empty purpose for {template_key}")

        rel_path = _validate_relative_path(file_rel, field_name=f"{template_key}.file")
        if rel_path.suffix != ".yml":
            raise ValueError(f"{catalog_rel}: file for {template_key} must end with .yml")
        if not str(rel_path).startswith(str(WORKFLOW_DIR) + "/"):
            raise ValueError(
                f"{catalog_rel}: file for {template_key} must be under {WORKFLOW_DIR.as_posix()}/"
            )
        expected_name = f"{template_key}.yml"
        if rel_path.name != expected_name:
            raise ValueError(
                f"{catalog_rel}: file name mismatch for {template_key}; expected {expected_name}, found {rel_path.name}"
            )

        if template_key in seen_keys:
            raise ValueError(f"{catalog_rel}: duplicate template_key '{template_key}'")
        if file_rel in seen_files:
            raise ValueError(f"{catalog_rel}: duplicate file entry '{file_rel}'")
        seen_keys.add(template_key)
        seen_files.add(file_rel)

        normalized.append(
            {
                "template_key": template_key,
                "file": file_rel,
                "archetype": archetype,
                "purpose": purpose,
            }
        )

    return catalog_path, payload, sorted(normalized, key=lambda item: item["template_key"])


def _catalog_workflow_files(repo_root: Path) -> list[str]:
    return sorted(
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / WORKFLOW_DIR).glob(TEMPLATE_PATTERN)
        if path.is_file()
    )


def run_check(*, repo_root: Path, catalog_rel: Path) -> tuple[int, dict[str, object]]:
    _catalog_path, payload, entries = _load_catalog(repo_root, catalog_rel)
    listed_files = [entry["file"] for entry in entries]
    listed_set = set(listed_files)

    missing_files = [rel for rel in listed_files if not (repo_root / rel).exists()]
    repo_files = _catalog_workflow_files(repo_root)
    untracked_files = [rel for rel in repo_files if rel not in listed_set]

    if missing_files or untracked_files:
        return (
            2,
            {
                "status": "BLOCKED",
                "message": "workflow template catalog is out of sync with filesystem",
                "missing_files": missing_files,
                "untracked_files": untracked_files,
            },
        )

    return (
        0,
        {
            "status": "OK",
            "schema": payload.get("schema"),
            "catalog_version": payload.get("catalog_version"),
            "template_count": len(entries),
            "template_keys": [entry["template_key"] for entry in entries],
        },
    )


def _scaffold_body(*, archetype: str, title: str) -> str:
    if archetype == "pr_gate_shadow_live_verify":
        return f"""name: {title}

on:
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  shadow-evaluate:
    name: Shadow Evaluate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: preview-only shadow evaluation"

  live-verify:
    name: Live Verify
    runs-on: ubuntu-latest
    needs: [shadow-evaluate]
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: collect evidence and run benchmark in --review-mode --evidence-dir"

  reviewer-recompute:
    name: Reviewer Recompute Gate
    runs-on: ubuntu-latest
    needs: [live-verify]
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: verify hashes and recompute gate from evidence"
"""
    if archetype == "pipeline_roles_hardened":
        return f"""name: {title}

on:
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  governance-developer:
    name: Governance Developer
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: collect evidence and run benchmark"

  governance-reviewer:
    name: Governance Reviewer (Authoritative Gate)
    runs-on: ubuntu-latest
    needs: [governance-developer]
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: hash-verify artifacts and recompute gate in review mode"
"""
    if archetype == "ruleset_release":
        return f"""name: {title}

on:
  workflow_dispatch:
  push:
    tags:
      - "ruleset-v*"

permissions:
  contents: write

jobs:
  validate-and-lock:
    name: Validate Manifests and Build Locks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: build deterministic ruleset lock and verify isolated parity"
"""
    if archetype == "golden_output_stability":
        return f"""name: {title}

on:
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  golden-output-stability:
    name: Golden Output Stability
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: generate outputs, compare against baseline, block drift"
"""
    if archetype == "golden_baseline_update":
        return f"""name: {title}

on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update-golden-baseline:
    name: Generate and Update Golden Baseline
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          set -euo pipefail
          echo "TODO: regenerate baseline and optionally commit update"
"""
    raise ValueError(f"unsupported archetype: {archetype}")


def run_scaffold(
    *,
    repo_root: Path,
    catalog_rel: Path,
    template_key: str,
    archetype: str,
    title: str,
    purpose: str,
    dry_run: bool,
) -> tuple[int, dict[str, object]]:
    if not TEMPLATE_KEY_RE.fullmatch(template_key):
        raise ValueError("template_key must match governance-<kebab-case>")
    if archetype not in ALLOWED_ARCHETYPES:
        raise ValueError(f"unsupported archetype '{archetype}'")
    if not purpose.strip():
        raise ValueError("purpose must be non-empty")

    catalog_path, payload, entries = _load_catalog(repo_root, catalog_rel)
    existing_keys = {entry["template_key"] for entry in entries}
    if template_key in existing_keys:
        raise ValueError(f"template_key already exists in catalog: {template_key}")

    file_rel = (WORKFLOW_DIR / f"{template_key}.yml").as_posix()
    file_path = repo_root / file_rel
    if file_path.exists():
        raise ValueError(f"target workflow already exists: {file_rel}")

    body = _scaffold_body(archetype=archetype, title=title)

    updated_entries = list(entries)
    updated_entries.append(
        {
            "template_key": template_key,
            "file": file_rel,
            "archetype": archetype,
            "purpose": purpose.strip(),
        }
    )
    updated_entries.sort(key=lambda item: item["template_key"])
    payload["templates"] = updated_entries

    if not dry_run:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(body, encoding="utf-8")
        _write_json(catalog_path, payload)

    return (
        0,
        {
            "status": "OK",
            "dry_run": dry_run,
            "created_template_key": template_key,
            "created_file": file_rel,
            "catalog": catalog_rel.as_posix(),
        },
    )


def _resolve_repo_root(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Governance GitHub Actions template validator and scaffold tool.")
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser("check", help="Validate template catalog consistency")
    check_parser.add_argument("--repo-root", default="")
    check_parser.add_argument("--catalog", default=str(CATALOG_PATH))

    scaffold_parser = subparsers.add_parser("scaffold", help="Create a new standardized workflow from archetype")
    scaffold_parser.add_argument("--repo-root", default="")
    scaffold_parser.add_argument("--catalog", default=str(CATALOG_PATH))
    scaffold_parser.add_argument("--template-key", required=True)
    scaffold_parser.add_argument("--archetype", required=True, choices=sorted(ALLOWED_ARCHETYPES))
    scaffold_parser.add_argument("--title", required=True)
    scaffold_parser.add_argument("--purpose", required=True)
    scaffold_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.command == "scaffold":
            code, payload = run_scaffold(
                repo_root=_resolve_repo_root(args.repo_root),
                catalog_rel=Path(args.catalog),
                template_key=args.template_key,
                archetype=args.archetype,
                title=args.title,
                purpose=args.purpose,
                dry_run=args.dry_run,
            )
        elif args.command == "check":
            code, payload = run_check(
                repo_root=_resolve_repo_root(args.repo_root),
                catalog_rel=Path(args.catalog),
            )
        else:
            code, payload = run_check(
                repo_root=_resolve_repo_root(None),
                catalog_rel=CATALOG_PATH,
            )
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "message": str(exc)}, ensure_ascii=True))
        return 2

    print(json.dumps(payload, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
