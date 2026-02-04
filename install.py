```python
#!/usr/bin/env python3
"""
LLM Governance System - Installer

Installs governance system files to the OpenCode config directory.

Target (Windows): %USERPROFILE%/.config/opencode   (PRIMARY, as requested)
Fallback (Windows): %APPDATA%/opencode
macOS/Linux: ${XDG_CONFIG_HOME:-~/.config}/opencode

Features:
- fail-closed precheck for required files
- --dry-run (no filesystem changes)
- --force (overwrite without prompt)
- --no-backup (disable backup on overwrite)
- optional --source-dir (defaults to script directory)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

VERSION = "1.1.0"

# Files expected in the source directory (script dir by default).
# These are the "core" governance files that should exist for a usable install.
REQUIRED_SOURCE_FILES = [
    "master.md",
    "rules.md",
    "start.md",
    "continue.md",
    "resume.md",
    "SESSION_STATE_SCHEMA.md",
    "QUALITY_INDEX.md",
    "CONFLICT_RESOLUTION.md",
]

# Additional files to copy if present (non-fatal if missing).
OPTIONAL_SOURCE_FILES = [
    "ADR.md",
    "TICKET_RECORD_TEMPLATE.md",
    "SCOPE-AND-CONTEXT.md",
    "ResumePrompt.md",
    "README-OPENCODE.md",
]

# Profile rulebooks: copied from <source>/profiles/*.md to <config>/commands/profiles/
PROFILE_GLOB = "*.md"


@dataclass(frozen=True)
class InstallPlan:
    config_root: Path
    commands_dir: Path
    profiles_dir: Path
    workspaces_dir: Path
    backup_dir: Path | None
    files_to_copy: List[Tuple[Path, Path]]  # (src, dst)
    profile_files_to_copy: List[Tuple[Path, Path]]  # (src, dst)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def get_config_root() -> Path:
    """
    Determine OpenCode config root based on OS.
    Windows primary: %USERPROFILE%/.config/opencode  (as per your requirement)
    Windows fallback: %APPDATA%/opencode
    macOS/Linux: ${XDG_CONFIG_HOME:-~/.config}/opencode
    """
    system = platform.system()

    if system == "Windows":
        userprofile = os.getenv("USERPROFILE")
        if userprofile:
            return Path(userprofile) / ".config" / "opencode"

        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / "opencode"

        raise RuntimeError("Windows detected but neither USERPROFILE nor APPDATA is set.")

    if system in ("Darwin", "Linux"):
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "opencode"
        return Path.home() / ".config" / "opencode"

    raise RuntimeError(f"Unsupported OS: {system}")


def ensure_dirs(dirs: Iterable[Path], dry_run: bool) -> None:
    for d in dirs:
        if dry_run:
            print(f"  [DRY-RUN] mkdir -p {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  ✅ {d}")


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def precheck_source(source_dir: Path) -> None:
    missing = [name for name in REQUIRED_SOURCE_FILES if not (source_dir / name).is_file()]
    if missing:
        msg = (
            "Missing required source files (fail-closed):\n"
            + "\n".join(f"  - {m}" for m in missing)
            + f"\nSource dir: {source_dir}"
        )
        raise FileNotFoundError(msg)


def build_plan(
    source_dir: Path,
    config_root: Path,
    enable_backup: bool,
) -> InstallPlan:
    commands_dir = config_root / "commands"
    profiles_dir = commands_dir / "profiles"
    workspaces_dir = config_root / "workspaces"

    backup_dir = None
    if enable_backup:
        backup_dir = commands_dir / f"backup-{timestamp()}"

    files_to_copy: List[Tuple[Path, Path]] = []
    for name in REQUIRED_SOURCE_FILES + OPTIONAL_SOURCE_FILES:
        src = source_dir / name
        if src.is_file():
            dst = commands_dir / name
            files_to_copy.append((src, dst))

    profile_files_to_copy: List[Tuple[Path, Path]] = []
    profile_src_dir = source_dir / "profiles"
    if profile_src_dir.is_dir():
        for src in sorted(profile_src_dir.glob(PROFILE_GLOB)):
            if src.is_file():
                dst = profiles_dir / src.name
                profile_files_to_copy.append((src, dst))

    return InstallPlan(
        config_root=config_root,
        commands_dir=commands_dir,
        profiles_dir=profiles_dir,
        workspaces_dir=workspaces_dir,
        backup_dir=backup_dir,
        files_to_copy=files_to_copy,
        profile_files_to_copy=profile_files_to_copy,
    )


def existing_targets(plan: InstallPlan) -> List[Path]:
    targets = [dst for _, dst in plan.files_to_copy] + [dst for _, dst in plan.profile_files_to_copy]
    return [p for p in targets if p.exists()]


def backup_existing(plan: InstallPlan, dry_run: bool) -> None:
    if plan.backup_dir is None:
        return

    targets = existing_targets(plan)
    if not targets:
        print("  (No existing files to backup.)")
        return

    if dry_run:
        print(f"  [DRY-RUN] create backup dir: {plan.backup_dir}")
    else:
        plan.backup_dir.mkdir(parents=True, exist_ok=True)

    for dst in targets:
        # Mirror structure under backup dir relative to commands_dir
        try:
            rel = dst.relative_to(plan.commands_dir)
            backup_path = plan.backup_dir / rel
        except ValueError:
            # Not under commands_dir (shouldn't happen here), just place by name
            backup_path = plan.backup_dir / dst.name

        if dry_run:
            print(f"  [DRY-RUN] backup {dst} -> {backup_path}")
        else:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup_path)
            print(f"  🧷 Backed up {dst.name} -> {backup_path}")


def copy_files(pairs: List[Tuple[Path, Path]], dry_run: bool) -> None:
    for src, dst in pairs:
        if dry_run:
            print(f"  [DRY-RUN] copy {src} -> {dst}")
        else:
            shutil.copy2(src, dst)
            print(f"  ✅ {dst.name}")


def validate_installation(plan: InstallPlan) -> bool:
    critical = [
        plan.commands_dir / "master.md",
        plan.commands_dir / "rules.md",
        plan.commands_dir / "start.md",
    ]
    ok = True
    for f in critical:
        if f.is_file():
            print(f"  ✅ {f.name}")
        else:
            print(f"  ❌ {f.name} MISSING!")
            ok = False
    return ok


def write_manifest(plan: InstallPlan, dry_run: bool) -> None:
    manifest = {
        "version": VERSION,
        "installedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "configRoot": str(plan.config_root),
        "commandsDir": str(plan.commands_dir),
        "profilesDir": str(plan.profiles_dir),
        "files": [],
    }

    for src, dst in plan.files_to_copy + plan.profile_files_to_copy:
        manifest["files"].append(
            {
                "src": str(src),
                "dst": str(dst),
                "existsAfter": dst.exists() if not dry_run else "unknown(dry-run)",
            }
        )

    manifest_path = plan.commands_dir / "INSTALL_MANIFEST.json"
    if dry_run:
        print(f"  [DRY-RUN] write manifest -> {manifest_path}")
        print("  [DRY-RUN] manifest preview (first 20 lines):")
        preview = json.dumps(manifest, indent=2).splitlines()[:20]
        for line in preview:
            print(f"    {line}")
        if len(json.dumps(manifest, indent=2).splitlines()) > 20:
            print("    ...")
        return

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"  🧾 Wrote manifest: {manifest_path.name}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install governance system files to OpenCode config directory.")
    p.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory containing governance files (default: script directory).",
    )
    p.add_argument(
        "--config-root",
        type=Path,
        default=None,
        help="Override config root (default: auto-detect).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen, but do not write anything.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite without interactive prompt.",
    )
    p.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable creating a backup when overwriting existing files.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 72)
    print("LLM Governance System Installer")
    print(f"Version {VERSION}")
    print("=" * 72)

    try:
        source_dir: Path = args.source_dir.resolve()
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

        print("\n🔍 Precheck source directory (fail-closed)...")
        precheck_source(source_dir)
        print("  ✅ Required source files present.")

        print("\n🔍 Detecting configuration directory...")
        config_root = (args.config_root.resolve() if args.config_root else get_config_root().resolve())
        print(f"  Config root: {config_root}")

        enable_backup = not args.no_backup
        plan = build_plan(source_dir=source_dir, config_root=config_root, enable_backup=enable_backup)

        print("\n📦 Installation plan:")
        print(f"  Commands:   {plan.commands_dir}")
        print(f"  Profiles:   {plan.profiles_dir}")
        print(f"  Workspaces: {plan.workspaces_dir}")
        print(f"  Backup:     {plan.backup_dir if plan.backup_dir else '(disabled)'}")
        print("\n  Files to copy:")
        for src, dst in plan.files_to_copy:
            print(f"   - {src.name} -> {dst}")
        if plan.profile_files_to_copy:
            print("\n  Profile files to copy:")
            for src, dst in plan.profile_files_to_copy:
                print(f"   - profiles/{src.name} -> {dst}")
        else:
            print("\n  Profile files to copy: (none found)")

        # Existing target detection
        targets = existing_targets(plan)
        if targets:
            print(f"\n⚠️  Detected {len(targets)} existing target file(s).")
            for t in targets[:15]:
                print(f"   - {t}")
            if len(targets) > 15:
                print("   ...")

        # Confirmation (unless --force or --dry-run)
        if not args.force and not args.dry_run:
            resp = input(f"\nProceed to install into {config_root}? [Y/n] ").strip().lower()
            if resp in ("n", "no"):
                print("Installation cancelled.")
                return 0

        print("\n📁 Creating directory structure...")
        ensure_dirs([plan.config_root, plan.commands_dir, plan.profiles_dir, plan.workspaces_dir], dry_run=args.dry_run)

        # Backup if overwriting and backup enabled
        if targets and enable_backup:
            print("\n🧷 Backing up existing files before overwrite...")
            backup_existing(plan, dry_run=args.dry_run)

        print("\n📋 Copying governance files...")
        copy_files(plan.files_to_copy, dry_run=args.dry_run)

        if plan.profile_files_to_copy:
            print("\n📋 Copying profile rulebooks...")
            copy_files(plan.profile_files_to_copy, dry_run=args.dry_run)

        print("\n🧾 Writing install manifest...")
        write_manifest(plan, dry_run=args.dry_run)

        print("\n🔍 Validating installation (critical files)...")
        if args.dry_run:
            print("  [DRY-RUN] Skipping post-install validation (no files written).")
            print("\n✅ Dry-run complete.")
            return 0

        if not validate_installation(plan):
            eprint("\n❌ Installation completed but validation failed (critical files missing).")
            return 2

        print("\n" + "=" * 72)
        print("🎉 Installation Complete!")
        print("=" * 72)
        print("\nNext steps:")
        print("  1) Ensure OpenCode points to this config root.")
        print("  2) Run /master or reference start.md (depending on your setup).")
        print("\nInstalled to:")
        print(f"  {plan.commands_dir}")
        print("\nManifest:")
        print(f"  {plan.commands_dir / 'INSTALL_MANIFEST.json'}")
        if (plan.commands_dir / "README-OPENCODE.md").exists():
            print("\nDocs:")
            print(f"  {plan.commands_dir / 'README-OPENCODE.md'}")
        return 0

    except Exception as e:
        eprint(f"\n❌ Installation failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```
