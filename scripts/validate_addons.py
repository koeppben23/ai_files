#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_CLASSES = {"required", "advisory"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_scalar(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not m:
        return None
    value = m.group(1).strip().strip('"').strip("'")
    return value or None


def _extract_signals_block(text: str) -> str | None:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^signals:\s*$", line):
            start = i + 1
            break
    if start is None:
        return None

    block: list[str] = []
    for line in lines[start:]:
        if line.strip() == "":
            block.append(line)
            continue
        if re.match(r"^\S", line):
            break
        block.append(line)
    return "\n".join(block)


def validate_manifest(path: Path, repo_root: Path) -> list[str]:
    text = read_text(path)
    errors: list[str] = []

    addon_key = _extract_scalar(text, "addon_key")
    addon_class = _extract_scalar(text, "addon_class")
    rulebook = _extract_scalar(text, "rulebook")

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

    block = _extract_signals_block(text)
    if block is None:
        errors.append("missing signals block")
    else:
        if re.search(r"^\s+(any|all):\s*$", block, flags=re.MULTILINE) is None:
            errors.append("signals block must define 'any:' or 'all:'")
        if re.search(r"^\s+-\s+", block, flags=re.MULTILINE) is None:
            errors.append("signals block must include at least one list entry")

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

        text = read_text(manifest)
        addon_key = _extract_scalar(text, "addon_key")
        if addon_key:
            if addon_key in seen_keys:
                errors.append(
                    f"duplicate addon_key={addon_key} (also in {seen_keys[addon_key].resolve().relative_to(repo_root).as_posix()})"
                )
            else:
                seen_keys[addon_key] = manifest

        if errors:
            failures.append(f"{rel}: " + "; ".join(errors))

    if failures:
        print("Addon manifest validation FAILED:", file=sys.stderr)
        for f in failures:
            print(f"- {f}", file=sys.stderr)
        return 1

    print(f"OK: validated {len(manifests)} addon manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
