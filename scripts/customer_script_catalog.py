#!/usr/bin/env python3
"""Validate and query the customer-relevant script catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


CATALOG_PATH = Path("diagnostics/CUSTOMER_SCRIPT_CATALOG.json")
CATALOG_SCHEMA = "governance.customer-script-catalog.v1"


def _load_catalog(repo_root: Path, catalog_rel: Path) -> dict[str, object]:
    path = repo_root / catalog_rel
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing catalog file: {catalog_rel}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {catalog_rel}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"catalog must be a JSON object: {catalog_rel}")
    if payload.get("schema") != CATALOG_SCHEMA:
        raise ValueError(
            f"catalog schema mismatch: expected {CATALOG_SCHEMA}, got {payload.get('schema')!r}"
        )
    scripts = payload.get("scripts")
    if not isinstance(scripts, list) or not scripts:
        raise ValueError("catalog scripts must be a non-empty list")
    return payload


def _normalize_entries(payload: dict[str, object], *, repo_root: Path) -> list[dict[str, object]]:
    raw_scripts = payload.get("scripts")
    assert isinstance(raw_scripts, list)
    normalized: list[dict[str, object]] = []
    seen_paths: set[str] = set()

    for idx, raw in enumerate(raw_scripts, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"scripts[{idx}] must be an object")

        required = ["path", "purpose", "customer_relevant", "ship_in_release", "tier"]
        missing = [name for name in required if name not in raw]
        if missing:
            raise ValueError(f"scripts[{idx}] missing fields: {missing}")

        path = str(raw["path"]).replace("\\", "/")
        purpose = str(raw["purpose"]).strip()
        tier = str(raw["tier"]).strip()
        customer_relevant = bool(raw["customer_relevant"])
        ship_in_release = bool(raw["ship_in_release"])

        if not path.startswith("scripts/"):
            raise ValueError(f"scripts[{idx}].path must be under scripts/: {path}")
        if path in seen_paths:
            raise ValueError(f"duplicate script path in catalog: {path}")
        seen_paths.add(path)
        if not purpose:
            raise ValueError(f"scripts[{idx}] purpose must be non-empty")
        if tier not in {"essential", "advanced", "internal"}:
            raise ValueError(f"scripts[{idx}] tier must be one of essential|advanced|internal")
        if ship_in_release and not customer_relevant:
            raise ValueError(f"scripts[{idx}] cannot ship_in_release=true with customer_relevant=false")
        if not (repo_root / path).is_file():
            raise ValueError(f"catalog references missing script file: {path}")

        normalized.append(
            {
                "path": path,
                "purpose": purpose,
                "customer_relevant": customer_relevant,
                "ship_in_release": ship_in_release,
                "tier": tier,
            }
        )

    return sorted(normalized, key=lambda item: str(item["path"]))


def run_check(*, repo_root: Path, catalog_rel: Path) -> tuple[int, dict[str, object]]:
    payload = _load_catalog(repo_root, catalog_rel)
    entries = _normalize_entries(payload, repo_root=repo_root)
    customer = [entry for entry in entries if bool(entry["customer_relevant"])]
    shipped = [entry for entry in entries if bool(entry["ship_in_release"])]

    return (
        0,
        {
            "status": "OK",
            "schema": CATALOG_SCHEMA,
            "catalog_version": payload.get("catalog_version"),
            "script_count": len(entries),
            "customer_relevant_count": len(customer),
            "ship_in_release_count": len(shipped),
        },
    )


def run_list(*, repo_root: Path, catalog_rel: Path, shipped_only: bool) -> tuple[int, dict[str, object]]:
    payload = _load_catalog(repo_root, catalog_rel)
    entries = _normalize_entries(payload, repo_root=repo_root)
    if shipped_only:
        entries = [entry for entry in entries if bool(entry["ship_in_release"])]
    else:
        entries = [entry for entry in entries if bool(entry["customer_relevant"])]

    return (
        0,
        {
            "status": "OK",
            "mode": "ship_in_release" if shipped_only else "customer_relevant",
            "scripts": entries,
        },
    )


def _resolve_repo_root(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and query customer-relevant script catalog.")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--catalog", default=str(CATALOG_PATH))

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("check", help="Validate catalog")
    list_parser = subparsers.add_parser("list", help="List customer-relevant scripts")
    list_parser.add_argument("--shipped-only", action="store_true", help="List only scripts shipped in release artifacts")

    args = parser.parse_args(argv)
    repo_root = _resolve_repo_root(args.repo_root)
    catalog_rel = Path(args.catalog)

    try:
        if args.command == "list":
            code, payload = run_list(repo_root=repo_root, catalog_rel=catalog_rel, shipped_only=args.shipped_only)
        else:
            code, payload = run_check(repo_root=repo_root, catalog_rel=catalog_rel)
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "message": str(exc)}, ensure_ascii=True))
        return 2

    print(json.dumps(payload, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
