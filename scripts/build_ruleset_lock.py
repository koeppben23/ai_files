"""Build deterministic ruleset manifest/lock/hash artifacts from repository sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_files(root: Path, pattern: str) -> list[Path]:
    return sorted([p for p in root.glob(pattern) if p.is_file()])


def _relative_posix(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def build_ruleset_artifacts(*, repo_root: Path, ruleset_id: str, version: str, output_root: Path) -> dict[str, str]:
    core_files = [repo_root / "master.md", repo_root / "rules.md", repo_root / "start.md"]
    missing_core = [_relative_posix(p, repo_root) for p in core_files if not p.exists()]
    if missing_core:
        raise ValueError(f"missing required core rulebook files: {', '.join(missing_core)}")

    profiles = _collect_files(repo_root, "profiles/rules*.md")
    addons = _collect_files(repo_root, "profiles/addons/*.addon.yml")
    if not profiles:
        raise ValueError("no profile rulebooks found under profiles/rules*.md")
    if not addons:
        raise ValueError("no addon manifests found under profiles/addons/*.addon.yml")

    source_files = sorted(core_files + profiles + addons)
    source_entries = [
        {
            "path": _relative_posix(path, repo_root),
            "sha256": _sha256(path),
        }
        for path in source_files
    ]

    profile_entries = [entry for entry in source_entries if entry["path"].startswith("profiles/rules")]
    addon_entries = [entry for entry in source_entries if entry["path"].startswith("profiles/addons/")]

    manifest = {
        "schema": "governance-ruleset-manifest.v1",
        "ruleset_id": ruleset_id,
        "version": version,
        "profile_count": len(profile_entries),
        "addon_count": len(addon_entries),
        "core_rulebook_count": len(source_entries) - len(profile_entries) - len(addon_entries),
        "source_file_count": len(source_entries),
        "source_files": source_entries,
        "profiles": profile_entries,
        "addons": addon_entries,
    }
    lock = {
        "schema": "governance-ruleset-lock.v1",
        "ruleset_id": ruleset_id,
        "version": version,
        "deterministic": True,
        "resolved_profiles": [entry["path"] for entry in profile_entries],
        "resolved_addons": [entry["path"] for entry in addon_entries],
        "resolved_core_rulebooks": [entry["path"] for entry in source_entries if entry["path"] in {"master.md", "rules.md", "start.md"}],
        "source_files": source_entries,
        "conflicts": [],
    }

    out = output_root / ruleset_id / version
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    lock_path = out / "lock.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    hashes = {
        "manifest.json": _sha256(manifest_path),
        "lock.json": _sha256(lock_path),
    }
    # ruleset_hash includes manifest/lock and every source file path+digest pair.
    digest_parts = [hashes["manifest.json"], hashes["lock.json"]]
    digest_parts.extend(f"{entry['path']}:{entry['sha256']}" for entry in source_entries)
    hashes["ruleset_hash"] = hashlib.sha256("".join(digest_parts).encode("utf-8")).hexdigest()

    hashes_path = out / "hashes.json"
    hashes_path.write_text(json.dumps(hashes, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic governance ruleset lock artifacts.")
    parser.add_argument("--ruleset-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo-root", default="", help="Repository root containing master.md/rules.md/profiles.")
    parser.add_argument("--output-root", default="rulesets")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.ruleset_id):
        print(json.dumps({"status": "BLOCKED", "message": "invalid ruleset-id"}, ensure_ascii=True))
        return 2
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.version):
        print(json.dumps({"status": "BLOCKED", "message": "version must be semver"}, ensure_ascii=True))
        return 2

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]
    hashes = build_ruleset_artifacts(
        repo_root=repo_root,
        ruleset_id=args.ruleset_id,
        version=args.version,
        output_root=Path(args.output_root),
    )
    print(json.dumps({"status": "OK", "ruleset_hash": hashes["ruleset_hash"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
