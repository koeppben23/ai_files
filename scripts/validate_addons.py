#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_CLASSES = {"required", "advisory"}
ALLOWED_SIGNAL_KEYS = {
    "file_glob",
    "maven_dep",
    "maven_dep_prefix",
    "code_regex",
    "config_key_prefix",
    "workflow_file",
}
ALLOWED_SURFACES = {
    "api_contract",
    "backend_java_templates",
    "backend_templates",
    "bdd_framework",
    "build_tooling",
    "db_migration",
    "e2e_test_framework",
    "frontend_api_client",
    "frontend_templates",
    "governance_docs",
    "linting",
    "messaging",
    "principal_review",
    "release",
    "risk_model",
    "scorecard_calibration",
    "security",
    "static",
    "test_framework",
}
ALLOWED_CAPABILITIES = {
    "angular",
    "cucumber",
    "cypress",
    "governance_docs",
    "java",
    "kafka",
    "liquibase",
    "nx",
    "openapi",
    "python",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _parse_inline_list(value: str) -> list[str] | None:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return None
    inner = value[1:-1].strip()
    if not inner:
        return []
    parts = [_unquote(p.strip()) for p in inner.split(",")]
    return [p for p in parts if p]


def parse_manifest(
    path: Path,
) -> tuple[dict[str, str], str | None, list[tuple[str, str]], dict[str, list[str]], list[str]]:
    """Parse constrained addon-manifest YAML shape without external dependencies."""
    text = read_text(path)
    scalars: dict[str, str] = {}
    signals_mode: str | None = None
    signals: list[tuple[str, str]] = []
    list_fields: dict[str, list[str]] = {
        "path_roots": [],
        "owns_surfaces": [],
        "touches_surfaces": [],
        "capabilities_any": [],
        "capabilities_all": [],
    }
    errors: list[str] = []

    in_signals = False
    active_list_key: str | None = None
    line_no = 0
    for raw in text.splitlines():
        line_no += 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # top-level key
        if not raw.startswith(" "):
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", raw)
            if not m:
                errors.append(f"line {line_no}: malformed top-level entry")
                continue
            key, val = m.group(1), m.group(2)
            if key == "signals":
                in_signals = True
                active_list_key = None
                continue
            if key in list_fields:
                in_signals = False
                if val:
                    parsed = _parse_inline_list(val)
                    if parsed is None:
                        errors.append(f"line {line_no}: {key} must be a YAML list")
                    else:
                        list_fields[key].extend(parsed)
                    active_list_key = None
                else:
                    active_list_key = key
                continue
            in_signals = False
            active_list_key = None
            val = _unquote(val)
            if not val:
                errors.append(f"line {line_no}: empty scalar for '{key}'")
                continue
            scalars[key] = val
            continue

        # nested signals block
        if in_signals:
            mode_match = re.match(r"^\s{2}(any|all):\s*$", raw)
            if mode_match:
                mode = mode_match.group(1)
                if signals_mode and signals_mode != mode:
                    errors.append(f"line {line_no}: mixed signals mode ('{signals_mode}' and '{mode}')")
                signals_mode = mode
                continue

            sig_match = re.match(r"^\s{4}-\s*([a-z_]+):\s*(.*?)\s*$", raw)
            if sig_match:
                if not signals_mode:
                    errors.append(f"line {line_no}: signal listed before any/all mode")
                    continue
                s_key = sig_match.group(1)
                s_val = _unquote(sig_match.group(2))
                if not s_val:
                    errors.append(f"line {line_no}: empty signal value for '{s_key}'")
                    continue
                signals.append((s_key, s_val))
                continue

            errors.append(f"line {line_no}: malformed signals entry")
            continue

        if active_list_key:
            root_match = re.match(r"^\s{2}-\s*(.*?)\s*$", raw)
            if root_match:
                root = _unquote(root_match.group(1))
                if not root:
                    errors.append(f"line {line_no}: empty {active_list_key} entry")
                else:
                    list_fields[active_list_key].append(root)
                continue

            errors.append(f"line {line_no}: malformed {active_list_key} entry")
            continue

        # any other indented block outside known structures
        errors.append(f"line {line_no}: unexpected indentation outside list/signals blocks")

    return scalars, signals_mode, signals, list_fields, errors


def validate_manifest(path: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    scalars, signals_mode, signals, list_fields, parse_errors = parse_manifest(path)
    errors.extend(parse_errors)

    addon_key = scalars.get("addon_key")
    addon_class = scalars.get("addon_class")
    rulebook = scalars.get("rulebook")
    manifest_version = scalars.get("manifest_version")

    if not addon_key:
        errors.append("missing addon_key")

    if not addon_class:
        errors.append("missing addon_class")
    elif addon_class not in ALLOWED_CLASSES:
        errors.append(f"invalid addon_class={addon_class} (expected one of: {sorted(ALLOWED_CLASSES)})")

    if not rulebook:
        errors.append("missing rulebook")
    else:
        rb_path = (repo_root / "profiles" / rulebook) if not rulebook.startswith("profiles/") else (repo_root / rulebook)
        if not rb_path.exists():
            errors.append(f"rulebook does not exist: {rulebook}")

    if not manifest_version:
        errors.append("missing manifest_version")
    elif not re.fullmatch(r"\d+", manifest_version):
        errors.append(f"invalid manifest_version={manifest_version} (expected integer)")
    elif int(manifest_version) != 1:
        errors.append(f"unsupported manifest_version={manifest_version} (expected 1)")

    path_roots = list_fields["path_roots"]
    if not path_roots:
        errors.append("missing path_roots")
    for root in path_roots:
        p = Path(root)
        if p.is_absolute():
            errors.append(f"path_roots entry must be relative: {root}")
        if root == "/":
            errors.append("path_roots entry must not be '/'")
        if ".." in p.parts:
            errors.append(f"path_roots entry must not contain traversal: {root}")

    owns_surfaces = list_fields["owns_surfaces"]
    touches_surfaces = list_fields["touches_surfaces"]
    if not owns_surfaces:
        errors.append("missing owns_surfaces")
    if not touches_surfaces:
        errors.append("missing touches_surfaces")

    for field_name, values in (("owns_surfaces", owns_surfaces), ("touches_surfaces", touches_surfaces)):
        seen = set()
        for value in values:
            if value in seen:
                errors.append(f"duplicate {field_name} entry: {value}")
            seen.add(value)
            if value not in ALLOWED_SURFACES:
                errors.append(f"unsupported {field_name} value: {value}")

    capabilities_any = list_fields["capabilities_any"]
    capabilities_all = list_fields["capabilities_all"]
    if not capabilities_any and not capabilities_all:
        errors.append("missing capabilities_any/capabilities_all (at least one required)")
    for field_name, values in (("capabilities_any", capabilities_any), ("capabilities_all", capabilities_all)):
        seen = set()
        for value in values:
            if value in seen:
                errors.append(f"duplicate {field_name} entry: {value}")
            seen.add(value)
            if value not in ALLOWED_CAPABILITIES:
                errors.append(f"unsupported {field_name} value: {value}")

    if signals_mode is None:
        errors.append("missing signals block")
    else:
        if signals_mode not in {"any", "all"}:
            errors.append("signals block must define 'any:' or 'all:'")
        if not signals:
            errors.append("signals block must include at least one list entry")
        for s_key, _s_val in signals:
            if s_key not in ALLOWED_SIGNAL_KEYS:
                errors.append(f"unsupported signal key: {s_key}")

    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate addon manifests under profiles/addons/*.addon.yml")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    manifests = sorted((repo_root / "profiles" / "addons").glob("*.addon.yml"))
    if not manifests:
        print("ERROR: no addon manifests found under profiles/addons/*.addon.yml", file=sys.stderr)
        return 2

    seen_keys: dict[str, Path] = {}
    failures: list[str] = []

    for manifest in manifests:
        rel = manifest.resolve().relative_to(repo_root).as_posix()
        errors = validate_manifest(manifest, repo_root)

        scalars, _signals_mode, _signals, list_fields, _parse_errors = parse_manifest(manifest)
        addon_key = scalars.get("addon_key")
        if addon_key:
            if addon_key in seen_keys:
                errors.append(
                    f"duplicate addon_key={addon_key} (also in {seen_keys[addon_key].resolve().relative_to(repo_root).as_posix()})"
                )
            else:
                seen_keys[addon_key] = manifest

        if errors:
            failures.append(f"{rel}: " + "; ".join(errors))

    # deterministic surface-ownership guard (fail fast)
    owners: dict[str, str] = {}
    used_caps: set[str] = set()
    cap_has_signal_mapping: dict[str, bool] = {c: False for c in ALLOWED_CAPABILITIES}
    for manifest in manifests:
        rel = manifest.resolve().relative_to(repo_root).as_posix()
        scalars, _m, _s, list_fields, _e = parse_manifest(manifest)
        addon_key = scalars.get("addon_key") or rel
        for surface in list_fields.get("owns_surfaces", []):
            existing = owners.get(surface)
            if existing and existing != addon_key:
                failures.append(
                    f"{rel}: owns_surfaces conflict on '{surface}' (also owned by addon_key={existing})"
                )
            else:
                owners[surface] = addon_key

        caps = set(list_fields.get("capabilities_any", []) + list_fields.get("capabilities_all", []))
        used_caps.update(caps)
        if _s:
            for cap in caps:
                if cap in cap_has_signal_mapping:
                    cap_has_signal_mapping[cap] = True

    missing_usage = sorted(c for c in ALLOWED_CAPABILITIES if c not in used_caps)
    if missing_usage:
        failures.append("capability catalog entries unused by manifests: " + ", ".join(missing_usage))

    missing_mapping = sorted(c for c, ok in cap_has_signal_mapping.items() if not ok)
    if missing_mapping:
        failures.append("capability catalog entries missing signal/evidence mapping: " + ", ".join(missing_mapping))

    if failures:
        print("Addon manifest validation FAILED:", file=sys.stderr)
        for f in failures:
            print(f"- {f}", file=sys.stderr)
        return 1

    print(f"OK: validated {len(manifests)} addon manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
