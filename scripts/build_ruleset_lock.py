"""Build deterministic ruleset manifest/lock/hash artifacts from repository sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import yaml
import jsonschema


def _resolve_rulesets_dir(repo_root: Path) -> Path:
    candidates = [repo_root / "governance_spec" / "rulesets", repo_root / "rulesets"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _resolve_addons_dir(repo_root: Path) -> Path:
    candidates = [repo_root / "governance_content" / "profiles" / "addons", repo_root / "profiles" / "addons"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _sha256(path: Path) -> str:
    # Normalize CRLF -> LF before hashing to match artifact_integrity verifier.
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def _collect_files(root: Path, pattern: str) -> list[Path]:
    return sorted([p for p in root.glob(pattern) if p.is_file()])


def _relative_posix(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def validate_against_schema(rulebook_path: Path, schema_path: Path) -> list[str]:
    """Validate a YAML rulebook against the JSON schema."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    rulebook = yaml.safe_load(rulebook_path.read_text(encoding="utf-8"))
    
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(rulebook))
    
    if errors:
        return [f"{e.json_path}: {e.message}" for e in errors]
    
    # Check schema_version compatibility: rulebook major must match schema major
    schema_ver = schema.get("version", "")
    rb_schema_ver = (rulebook.get("metadata") or {}).get("schema_version", "")
    if schema_ver and rb_schema_ver:
        schema_major = schema_ver.split(".")[0]
        rb_major = rb_schema_ver.split(".")[0]
        if schema_major != rb_major:
            return [
                f"schema_version mismatch: rulebook targets {rb_schema_ver} "
                f"but schema is {schema_ver} (major version differs)"
            ]
    
    return []


def build_ruleset_artifacts_v2(*, repo_root: Path, ruleset_id: str, version: str, output_root: Path) -> dict[str, str]:
    """Build artifacts using YAML/JSON rulebooks (v2 schema)."""
    
    schema_path = repo_root / "schemas" / "rulebook.schema.json"
    if not schema_path.exists():
        raise ValueError(f"schema not found: {schema_path}")
    
    rulesets_dir = _resolve_rulesets_dir(repo_root)
    if not rulesets_dir.exists():
        raise ValueError(f"rulesets directory not found: {rulesets_dir}")
    
    core_rulebooks = _collect_files(rulesets_dir / "core", "*.yml")
    profile_rulebooks = _collect_files(rulesets_dir / "profiles", "*.yml")
    
    if not core_rulebooks:
        raise ValueError("no core rulebooks found under rulesets/core/*.yml")
    if not profile_rulebooks:
        raise ValueError("no profile rulebooks found under rulesets/profiles/*.yml")
    
    validation_errors = []
    validated_rulebooks = []
    
    for rb_path in core_rulebooks + profile_rulebooks:
        errors = validate_against_schema(rb_path, schema_path)
        if errors:
            validation_errors.extend([f"{rb_path.name}: {e}" for e in errors])
        else:
            validated_rulebooks.append(rb_path)
    
    if validation_errors:
        raise ValueError(f"schema validation failed:\n" + "\n".join(validation_errors))
    
    # Extract schema version from schema file for manifest
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
    rulebook_schema_version = schema_data.get("version", "unknown")
    
    addons_dir = _resolve_addons_dir(repo_root)
    addons = _collect_files(addons_dir, "*.addon.yml")
    if not addons:
        raise ValueError(f"no addon manifests found under {addons_dir.relative_to(repo_root)}/*.addon.yml")
    
    source_files = sorted(validated_rulebooks + addons)
    source_entries = [
        {
            "path": _relative_posix(path, repo_root),
            "sha256": _sha256(path),
        }
        for path in source_files
    ]
    
    profile_entries = [entry for entry in source_entries if "profiles" in entry["path"]]
    addon_entries = [entry for entry in source_entries if "addons" in entry["path"]]
    core_entries = [entry for entry in source_entries if "core" in entry["path"]]
    
    manifest = {
        "schema": "governance-ruleset-manifest.v2",
        "ruleset_id": ruleset_id,
        "version": version,
        "rulebook_schema_version": rulebook_schema_version,
        "source_type": "yaml",
        "profile_count": len(profile_entries),
        "addon_count": len(addon_entries),
        "core_rulebook_count": len(core_entries),
        "source_file_count": len(source_entries),
        "source_files": source_entries,
        "profiles": profile_entries,
        "addons": addon_entries,
        "core_rulebooks": core_entries,
    }
    
    lock = {
        "schema": "governance-ruleset-lock.v2",
        "ruleset_id": ruleset_id,
        "version": version,
        "deterministic": True,
        "source_type": "yaml",
        "resolved_profiles": [entry["path"] for entry in profile_entries],
        "resolved_addons": [entry["path"] for entry in addon_entries],
        "resolved_core_rulebooks": [entry["path"] for entry in core_entries],
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
    
    digest_parts = [hashes["manifest.json"], hashes["lock.json"]]
    digest_parts.extend(f"{entry['path']}:{entry['sha256']}" for entry in source_entries)
    hashes["ruleset_hash"] = hashlib.sha256("".join(digest_parts).encode("utf-8")).hexdigest()
    
    hashes_path = out / "hashes.json"
    hashes_path.write_text(json.dumps(hashes, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic governance ruleset lock artifacts (v2 YAML schema).")
    parser.add_argument("--ruleset-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo-root", default="", help="Repository root containing rulesets/profiles YAML rulebooks.")
    parser.add_argument("--output-root", default="rulesets")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.ruleset_id):
        print(json.dumps({"status": "BLOCKED", "message": "invalid ruleset-id"}, ensure_ascii=True))
        return 2
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.version):
        print(json.dumps({"status": "BLOCKED", "message": "version must be semver"}, ensure_ascii=True))
        return 2

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[1]

    try:
        hashes = build_ruleset_artifacts_v2(
            repo_root=repo_root,
            ruleset_id=args.ruleset_id,
            version=args.version,
            output_root=Path(args.output_root),
        )
        print(json.dumps({"status": "OK", "ruleset_hash": hashes["ruleset_hash"], "mode": "v2-yaml"}, ensure_ascii=True))
        return 0
    except Exception as e:
        print(json.dumps({"status": "BLOCKED", "message": str(e)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
