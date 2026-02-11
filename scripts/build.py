from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP timestamps
FIXED_MTIME = 0                       # deterministic TAR/GZ mtime


EXCLUDE_DIRS = {
    ".git",
    ".github",
    "dist",
    "tests",
    "scripts",
    "__MACOSX",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}

FORBIDDEN_METADATA_SEGMENTS = ("__MACOSX",)
FORBIDDEN_METADATA_FILENAMES = {".DS_Store", "Icon\r"}


def is_forbidden_metadata_path(relpath: str) -> bool:
    """Return True for macOS metadata payload paths forbidden in artifacts."""

    normalized = relpath.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if any(part in FORBIDDEN_METADATA_SEGMENTS for part in parts):
        return True
    if any(part in FORBIDDEN_METADATA_FILENAMES for part in parts):
        return True
    if any(part.startswith("._") for part in parts):
        return True
    return False


def _enforce_metadata_hygiene_on_files(files: Iterable[Path], repo_root: Path) -> None:
    """Fail closed if selected release files contain forbidden metadata entries."""

    offenders = []
    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        if is_forbidden_metadata_path(rel):
            offenders.append(rel)
    if offenders:
        raise SystemExit(
            "Release metadata hygiene violation: forbidden files selected: " + ", ".join(sorted(offenders))
        )


def _enforce_metadata_hygiene_on_archive(artifact: Path, *, format_name: str) -> None:
    """Fail closed if built archive still contains forbidden metadata paths."""

    names: list[str] = []
    if format_name == "zip":
        with zipfile.ZipFile(artifact, "r") as zf:
            names = [n for n in zf.namelist() if n and not n.endswith("/")]
    elif format_name == "tar.gz":
        with tarfile.open(artifact, "r:gz") as tf:
            names = [m.name for m in tf.getmembers() if m.name and not m.isdir()]
    else:
        raise ValueError(f"unsupported artifact format for hygiene check: {format_name}")

    offenders = [name for name in names if is_forbidden_metadata_path(name)]
    if offenders:
        raise SystemExit(
            f"Release metadata hygiene violation in {artifact.name}: " + ", ".join(sorted(offenders))
        )


@dataclass(frozen=True)
class BuildPaths:
    repo_root: Path
    dist_dir: Path


def _read_governance_version(master_md: Path) -> str:
    if not master_md.exists():
        raise SystemExit("master.md not found (required for build)")

    head = "\n".join(master_md.read_text(encoding="utf-8").splitlines()[:80])
    m = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        head,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not m:
        raise SystemExit("Missing governance version in master.md (expected '# Governance-Version: <semver>' near the top).")
    return m.group(1)


def _is_excluded(path: Path, repo_root: Path) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    if any(part.startswith(".tmp_dist") for part in rel.parts):
        return True
    # Exclude AppleDouble sidecar files (resource-fork metadata).
    if any(part.startswith("._") for part in rel.parts):
        return True
    # Exclude macOS Finder metadata files.
    if any(part == "Icon\r" for part in rel.parts):
        return True
    return False


def _should_include_file(p: Path, rel: str) -> bool:
    name = p.name
    if name == "install.py":
        return True
    if name.upper().startswith("LICENSE") or name.upper().startswith("LICENCE"):
        return True
    # Addon manifests are required at runtime for deterministic addon activation/reload.
    if rel.startswith("profiles/addons/") and name.endswith(".addon.yml"):
        return True
    # Diagnostics runtime helpers are required for /start auto-persistence and error logging.
    if rel.startswith("diagnostics/") and p.suffix.lower() == ".py":
        return True
    if p.suffix.lower() in {".md", ".json"}:
        return True
    return False


def _is_under(path: Path, root: Path) -> bool:
    """Return True when path is located under root."""

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def collect_release_files(repo_root: Path, *, excluded_roots: tuple[Path, ...] = ()) -> list[Path]:
    """
    Allowlist strategy:
      - include: install.py, LICENSE*, LICENCE*, *.md, *.json,
        profiles/addons/*.addon.yml, diagnostics/*.py
      - exclude: .git, .github, dist, tests, scripts, caches
    Deterministic ordering (sorted by posix relpath).
    """
    out: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if any(_is_under(p, ex) for ex in excluded_roots):
            continue
        if _is_excluded(p, repo_root):
            continue
        rel = p.relative_to(repo_root).as_posix()
        if _should_include_file(p, rel):
            out.append(p)

    def key(x: Path) -> str:
        return x.relative_to(repo_root).as_posix()

    out = sorted(out, key=key)
    if not out:
        raise SystemExit("No files selected for release artifact (check include/exclude rules).")
    _enforce_metadata_hygiene_on_files(out, repo_root)
    return out


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_zip(out_zip: Path, prefix: str, repo_root: Path, files: list[Path]) -> None:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in files:
            rel = src.relative_to(repo_root).as_posix()
            arc = f"{prefix}/{rel}"

            zi = zipfile.ZipInfo(arc)
            zi.date_time = FIXED_ZIP_DT
            zi.compress_type = zipfile.ZIP_DEFLATED

            # Deterministic, minimal permission model:
            # - install.py executable
            # - everything else 0644
            mode = 0o755 if src.name == "install.py" else 0o644
            zi.external_attr = (mode & 0xFFFF) << 16

            with src.open("rb") as fsrc, zf.open(zi, "w") as fdst:
                shutil.copyfileobj(fsrc, fdst)


def write_tar_gz(out_tgz: Path, prefix: str, repo_root: Path, files: list[Path]) -> None:
    out_tgz.parent.mkdir(parents=True, exist_ok=True)
    with out_tgz.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=FIXED_MTIME) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tf:
                for src in files:
                    rel = src.relative_to(repo_root).as_posix()
                    arc = f"{prefix}/{rel}"

                    ti = tf.gettarinfo(str(src), arcname=arc)
                    ti.mtime = FIXED_MTIME
                    ti.uid = 0
                    ti.gid = 0
                    ti.uname = ""
                    ti.gname = ""
                    ti.mode = 0o755 if src.name == "install.py" else 0o644

                    with src.open("rb") as f:
                        tf.addfile(ti, fileobj=f)


def write_sha256sums(dist_dir: Path, artifacts: list[Path]) -> Path:
    out = dist_dir / "SHA256SUMS.txt"
    lines = []
    for a in artifacts:
        h = sha256_file(a)
        lines.append(f"{h}  {a.name}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_verification_report(dist_dir: Path, artifacts: list[Path]) -> Path:
    """Write machine-readable verification report sidecar for release artifacts."""

    artifact_hashes = {a.name: sha256_file(a) for a in artifacts}
    report = {
        "schema": "governance-verification-report.v1",
        "pytest_summary": os.environ.get("OPENCODE_PYTEST_SUMMARY", "not_provided"),
        "golden_summary": os.environ.get("OPENCODE_GOLDEN_SUMMARY", "not_provided"),
        "e2e_summary": os.environ.get("OPENCODE_E2E_SUMMARY", "not_provided"),
        "governance_lint": os.environ.get("OPENCODE_GOVERNANCE_LINT", "not_provided"),
        "artifact_hashes": artifact_hashes,
    }
    out = dist_dir / "verification-report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build deterministic release artifacts (zip + tar.gz).")
    p.add_argument("--out-dir", default="dist", help="Output directory (default: dist)")
    p.add_argument("--formats", default="zip,tar.gz", help="Comma-separated: zip, tar.gz (default: zip,tar.gz)")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = (repo_root / args.out_dir).resolve()
    bp = BuildPaths(repo_root=repo_root, dist_dir=dist_dir)

    version = _read_governance_version(bp.repo_root / "master.md")
    prefix = f"governance-{version}"

    files = collect_release_files(bp.repo_root, excluded_roots=(bp.dist_dir,))

    formats = [s.strip().lower() for s in str(args.formats).split(",") if s.strip()]
    artifacts: list[Path] = []

    if "zip" in formats:
        out_zip = bp.dist_dir / f"{prefix}.zip"
        write_zip(out_zip, prefix=prefix, repo_root=bp.repo_root, files=files)
        _enforce_metadata_hygiene_on_archive(out_zip, format_name="zip")
        artifacts.append(out_zip)

    if "tar.gz" in formats or "tgz" in formats:
        out_tgz = bp.dist_dir / f"{prefix}.tar.gz"
        write_tar_gz(out_tgz, prefix=prefix, repo_root=bp.repo_root, files=files)
        _enforce_metadata_hygiene_on_archive(out_tgz, format_name="tar.gz")
        artifacts.append(out_tgz)

    sums = write_sha256sums(bp.dist_dir, artifacts)
    verification = write_verification_report(bp.dist_dir, artifacts)
    
    def _pretty(p: Path) -> str:
        """Pretty-print artifact paths without assuming they live under repo_root."""
        try:
            return str(p.relative_to(bp.repo_root))
        except ValueError:
            return str(p)

    print("✅ Built artifacts:")
    for a in artifacts:
        print(f"  - {_pretty(a)}")
    print(f"  - {_pretty(sums)}")
    print(f"  - {_pretty(verification)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
