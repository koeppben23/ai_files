#!/usr/bin/env python3
"""
Release helper for the Governance System.

Goals:
- Single command that updates all version sources consistently:
  - master.md (Governance-Version header)
  - install.py (VERSION constant)
  - CHANGELOG.md (Keep-a-Changelog: cut [Unreleased] into new version section)
- Optionally commit + tag (annotated) the release.

Design:
- Fail-closed by default (empty unreleased changes => abort), unless --allow-empty-changelog.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import tempfile
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


SEMVERISH_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=False, check=check)


def replace_master_version(master_path: Path, version: str) -> bool:
    """
    Replace the first occurrence of:
      Governance-Version: <...>
    near the top, but we allow it anywhere to be robust.
    """
    text = read_text(master_path)
    # Match a line that contains Governance-Version: <token>
    pat = re.compile(r"^(.*Governance-Version:\s*)(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    m = pat.search(text)
    if not m:
        return False
    new_text = pat.sub(lambda m: f"{m.group(1)}{version}", text, count=1)
    if new_text != text:
        write_text(master_path, new_text)
    return True


def replace_install_version(install_path: Path, version: str) -> bool:
    text = read_text(install_path)
    pat = re.compile(r'^(VERSION\s*=\s*")([^"]+)(")\s*$', re.MULTILINE)
    m = pat.search(text)
    if not m:
        return False
    new_text = pat.sub(lambda m: f'{m.group(1)}{version}{m.group(3)}', text, count=1)
    if new_text != text:
        write_text(install_path, new_text)
    return True


def changelog_has_bullets(block: str) -> bool:
    """
    Consider any line that looks like a bullet as a "real change".
    """
    for line in block.splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")):
            return True
    return False


def cut_changelog_unreleased(changelog_path: Path, version: str, date_str: str, allow_empty: bool) -> None:
    """
    Keep-a-Changelog format:
      ## [Unreleased]
      ...content...
      ## [x.y.z] - YYYY-MM-DD
      ...content...

    We:
      - locate the [Unreleased] section
      - extract its body until the next '## [' heading (or EOF)
      - ensure it contains at least 1 bullet (unless allow_empty)
      - create a new section directly after [Unreleased] with extracted body
      - leave [Unreleased] in place, but empty (template preserved if present)
    """
    text = read_text(changelog_path)

    # Find the "## [Unreleased]" heading
    unreleased_heading = re.search(r"^##\s+\[Unreleased\]\s*$", text, flags=re.MULTILINE)
    if not unreleased_heading:
        raise RuntimeError("CHANGELOG.md: Missing '## [Unreleased]' heading.")

    start = unreleased_heading.end()
    # Find next version heading after Unreleased
    nxt = re.search(r"^##\s+\[[^\]]+\].*$", text[start:], flags=re.MULTILINE)
    end = start + (nxt.start() if nxt else len(text[start:]))

    unreleased_body = text[start:end]

    # Guard: don't allow releasing with empty Unreleased unless allow_empty
    if not changelog_has_bullets(unreleased_body):
        if not allow_empty:
            raise RuntimeError(
                "CHANGELOG.md: [Unreleased] contains no bullet entries. "
                "Add at least one bullet or use --allow-empty-changelog."
            )
        # Add a minimal, explicit bullet to satisfy strict release gates.
        # (Keeps a clean audit trail.)
        if unreleased_body.strip() == "":
            unreleased_body = "\n- No user-facing changes.\n"
        else:
            # Append one bullet at the end of Unreleased content
            unreleased_body = unreleased_body.rstrip() + "\n\n- No user-facing changes.\n"

    # Prevent duplicate section for the same version
    if re.search(rf"^##\s+\[{re.escape(version)}\]\b", text, flags=re.MULTILINE):
        raise RuntimeError(f"CHANGELOG.md: Section for [{version}] already exists.")

    new_section = f"\n## [{version}] - {date_str}\n" + unreleased_body.strip("\n") + "\n"

    # Rebuild:
    before = text[:start]
    after = text[end:]

    # Empty out Unreleased body but keep a clean single blank line
    new_text = before + "\n" + new_section + after

    # Ensure trailing newline
    if not new_text.endswith("\n"):
        new_text += "\n"

    write_text(changelog_path, new_text)


def ensure_clean_git_state() -> None:
    # refuse to operate on a dirty tree (professional, avoids partial updates)
    r = subprocess.run(["git", "status", "--porcelain"], text=True, capture_output=True, check=True)
    if r.stdout.strip():
        raise RuntimeError("Working tree is not clean. Commit/stash changes before releasing.")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Cut a release: bump versions + cut changelog + (optional) commit/tag.")
    ap.add_argument("--version", required=True, help="Release version (e.g. 1.0.0, 1.0.0-RC.1)")
    ap.add_argument("--date", default=None, help="Release date YYYY-MM-DD (default: today)")
    ap.add_argument("--allow-empty-changelog", action="store_true", help="Allow release even if [Unreleased] has no bullets.")
    ap.add_argument("--no-commit", action="store_true", help="Do not create a git commit.")
    ap.add_argument("--no-tag", action="store_true", help="Do not create an annotated git tag.")
    ap.add_argument("--tag-prefix", default="v", help="Tag prefix (default: v -> vX.Y.Z)")
    ap.add_argument("--message", default=None, help="Release commit message (default: chore(release): v<version>)")
    ap.add_argument("--dry-run", action="store_true", help="Show what would change without writing files or git ops.")
    args = ap.parse_args(argv)

    version = args.version.strip()
    if not SEMVERISH_RE.match(version):
        eprint(f"❌ Invalid version '{version}'. Expected semver-ish: X.Y.Z[-pre][+meta]")
        return 2

    date_str = args.date or _dt.date.today().isoformat()
    try:
        _dt.date.fromisoformat(date_str)
    except ValueError:
        eprint(f"❌ Invalid --date '{date_str}'. Expected YYYY-MM-DD.")
        return 2

    master_path = REPO_ROOT / "master.md"
    install_path = REPO_ROOT / "install.py"
    changelog_path = REPO_ROOT / "CHANGELOG.md"

    for p in (master_path, install_path, changelog_path):
        if not p.exists():
            eprint(f"❌ Missing required file: {p}")
            return 2

    try:
        ensure_clean_git_state()
    except Exception as e:
        eprint(f"❌ {e}")
        return 2

    # Load originals for dry-run diff preview
    orig_master = read_text(master_path)
    orig_install = read_text(install_path)
    orig_changelog = read_text(changelog_path)

    # Apply transforms in-memory first (so we can dry-run)
    # We'll write via helpers unless dry-run.
    try:
        # master.md
        if not re.search(r"Governance-Version:", orig_master, flags=re.IGNORECASE):
            raise RuntimeError("master.md: Missing 'Governance-Version:' header.")

        # install.py
        if not re.search(r'VERSION\s*=\s*"', orig_install):
            raise RuntimeError('install.py: Missing VERSION = "..." constant.')

        # For dry-run, we simulate by writing to temp strings via regex ops
        # 1) master
        new_master = re.sub(
            r"^(.*Governance-Version:\s*)(.+?)\s*$",
            lambda m: f"{m.group(1)}{version}",
            orig_master,
            count=1,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        # 2) install
        new_install = re.sub(
            r'^(VERSION\s*=\s*")([^"]+)(")\s*$',
            lambda m: f'{m.group(1)}{version}{m.group(3)}',
            orig_install,
            count=1,
            flags=re.MULTILINE,
        )

        # 3) changelog
        if args.dry_run:
            # Perform the real rewrite against a temp copy to catch the same failures as live mode.
            with tempfile.TemporaryDirectory() as td:
                tmp_changelog = Path(td) / "CHANGELOG.md"
                write_text(tmp_changelog, orig_changelog)
                cut_changelog_unreleased(
                    tmp_changelog,
                    version,
                    date_str,
                    allow_empty=args.allow_empty_changelog,
                )
        else:
            # write master/install first, then cut changelog using file-based function
            ok_m = replace_master_version(master_path, version)
            ok_i = replace_install_version(install_path, version)
            if not ok_m:
                raise RuntimeError("master.md: Could not replace Governance-Version.")
            if not ok_i:
                raise RuntimeError("install.py: Could not replace VERSION.")
            cut_changelog_unreleased(changelog_path, version, date_str, allow_empty=args.allow_empty_changelog)

    except Exception as e:
        eprint(f"❌ Release prep failed: {e}")
        return 3

    if args.dry_run:
        print("=== DRY RUN ===")
        print(f"Would set version: {version}")
        print(f"Would set date:    {date_str}")
        if new_master != orig_master:
            print(" - master.md would change")
        if new_install != orig_install:
            print(" - install.py would change")
        print(" - CHANGELOG.md would be cut (Unreleased -> new version section)")
        print("No files written, no git operations performed.")
        return 0

    # git commit + tag
    commit_msg = args.message or f"chore(release): {args.tag_prefix}{version}"
    tag = f"{args.tag_prefix}{version}"

    if not args.no_commit:
        run(["git", "add", "master.md", "install.py", "CHANGELOG.md"])
        run(["git", "commit", "-m", commit_msg])
        print(f"✅ Created release commit: {commit_msg}")
    else:
        print("ℹ️  --no-commit set: not creating commit")

    if not args.no_tag:
        # annotated tag
        run(["git", "tag", "-a", tag, "-m", tag])
        print(f"✅ Created tag: {tag}")
    else:
        print("ℹ️  --no-tag set: not creating tag")

    print("\nNext steps:")
    print(f"  - Push commit: git push origin HEAD")
    if not args.no_tag:
        print(f"  - Push tag:    git push origin {tag}")
    print("  - Build:       python scripts/build.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
