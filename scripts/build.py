from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP timestamps
FIXED_MTIME = 0                       # deterministic TAR/GZ mtime


EXCLUDE_DIRS = {
    ".git",
    ".github",
    "dist",
    "tests",
    "scripts",
    "__pycache__",
    ".pytest_cache",
    ".venv",
}


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
    return any(part in EXCLUDE_DIRS for part in rel.parts)


def _should_include_file(p: Path) -> bool:
    name = p.name
    if name == "install.py":
        return True
    if name.upper().startswith("LICENSE") or name.upper().startswith("LICENCE"):
        return True
    if p.suffix.lower() in {".md", ".json"}:
        return True
    return False


def collect_release_files(repo_root: Path) -> list[Path]:
    """
    Allowlist strategy:
      - include: install.py, LICENSE*, LICENCE*, *.md, *.json
      - exclude: .git, .github, dist, tests, scripts, caches
    Deterministic ordering (sorted by posix relpath).
    """
    out: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if _is_excluded(p, repo_root):
            continue
        if _should_include_file(p):
            out.append(p)

    def key(x: Path) -> str:
        return x.relative_to(repo_root).as_posix()

    out = sorted(out, key=key)
    if not out:
        raise SystemExit("No files selected for release artifact (check include/exclude rules).")
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

    files = collect_release_files(bp.repo_root)

    formats = [s.strip().lower() for s in str(args.formats).split(",") if s.strip()]
    artifacts: list[Path] = []

    if "zip" in formats:
        out_zip = bp.dist_dir / f"{prefix}.zip"
        write_zip(out_zip, prefix=prefix, repo_root=bp.repo_root, files=files)
        artifacts.append(out_zip)

    if "tar.gz" in formats or "tgz" in formats:
        out_tgz = bp.dist_dir / f"{prefix}.tar.gz"
        write_tar_gz(out_tgz, prefix=prefix, repo_root=bp.repo_root, files=files)
        artifacts.append(out_tgz)

    sums = write_sha256sums(bp.dist_dir, artifacts)

    print("✅ Built artifacts:")
    def _pretty(p: Path) -> str:
        try:
            return str(p.relative_to(bp.repo_root))
        except ValueError:
            return str(p)
    for a in artifacts:
        print(f"  - {_pretty(a)}")
    print(f"  - {_pretty(sums)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
