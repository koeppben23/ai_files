#!/usr/bin/env python3
"""Build a customer install bundle from release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path


FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)
BUNDLE_SCHEMA = "governance.customer-install-bundle.v1"


def _read_version(master_md: Path) -> str:
    if not master_md.exists():
        raise SystemExit("master.md not found")
    head = "\n".join(master_md.read_text(encoding="utf-8").splitlines()[:80])
    match = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        head,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        raise SystemExit("Missing Governance-Version in master.md")
    return match.group(1)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_sha256sums(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"Missing checksum file: {path}")

    sums: dict[str, str] = {}
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", stripped)
        if not match:
            raise SystemExit(f"Invalid checksum line {idx} in {path.name}: {line}")
        sums[match.group(2)] = match.group(1).lower()
    if not sums:
        raise SystemExit(f"Checksum file has no entries: {path}")
    return sums


def _verify_artifact_checksums(*, artifacts: list[Path], sums: dict[str, str]) -> None:
    missing: list[str] = []
    mismatched: list[str] = []
    for artifact in artifacts:
        expected = sums.get(artifact.name)
        if expected is None:
            missing.append(artifact.name)
            continue
        actual = _sha256(artifact)
        if actual != expected:
            mismatched.append(f"{artifact.name}: expected={expected} actual={actual}")

    if missing:
        raise SystemExit("SHA256SUMS.txt missing artifact entries: " + ", ".join(sorted(missing)))
    if mismatched:
        raise SystemExit("Artifact checksum mismatch: " + "; ".join(mismatched))


def _verify_report_hashes(*, report: Path, artifacts: list[Path]) -> None:
    if not report.exists():
        raise SystemExit(f"Missing verification report: {report}")

    payload = json.loads(report.read_text(encoding="utf-8"))
    if payload.get("schema") != "governance-verification-report.v1":
        raise SystemExit("verification-report.json schema mismatch")

    artifact_hashes = payload.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict):
        raise SystemExit("verification-report.json missing artifact_hashes object")

    for artifact in artifacts:
        expected = artifact_hashes.get(artifact.name)
        if not isinstance(expected, str):
            raise SystemExit(f"verification-report.json missing hash for {artifact.name}")
        actual = _sha256(artifact)
        if actual != expected:
            raise SystemExit(
                f"verification-report hash mismatch for {artifact.name}: expected={expected} actual={actual}"
            )


def _install_sh(archive_name: str, extracted_dir: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
BUNDLE_ROOT="$(cd -- "${{SCRIPT_DIR}}/.." && pwd)"
ARTIFACT_DIR="${{BUNDLE_ROOT}}/artifacts"
ARCHIVE_PATH="${{ARTIFACT_DIR}}/{archive_name}"
SUMS_PATH="${{ARTIFACT_DIR}}/SHA256SUMS.txt"
PYTHON_CMD="${{PYTHON_COMMAND:-python3}}"

if [[ ! -f "${{ARCHIVE_PATH}}" ]]; then
  echo "Missing archive: ${{ARCHIVE_PATH}}" >&2
  exit 1
fi

"${{PYTHON_CMD}}" - "${{ARCHIVE_PATH}}" "${{SUMS_PATH}}" <<'PY'
import hashlib
import pathlib
import sys

archive = pathlib.Path(sys.argv[1])
sums = pathlib.Path(sys.argv[2])
expected = None
for line in sums.read_text(encoding="utf-8").splitlines():
    parts = line.strip().split()
    if len(parts) >= 2 and parts[-1].lstrip("*") == archive.name:
        expected = parts[0].lower()
        break
if expected is None:
    raise SystemExit(f"SHA256SUMS entry not found for {{archive.name}}")
actual = hashlib.sha256(archive.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"Checksum mismatch for {{archive.name}}: expected={{expected}} actual={{actual}}")
PY

TMP_DIR="${{BUNDLE_ROOT}}/_tmp_install"
rm -rf "${{TMP_DIR}}"
mkdir -p "${{TMP_DIR}}"

"${{PYTHON_CMD}}" - "${{ARCHIVE_PATH}}" "${{TMP_DIR}}" <<'PY'
import pathlib
import sys
import zipfile

archive = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(archive, "r") as zf:
    zf.extractall(target)
PY

EXTRACTED_ROOT="${{TMP_DIR}}/{extracted_dir}"
INSTALL_PY="${{EXTRACTED_ROOT}}/install.py"
if [[ ! -f "${{INSTALL_PY}}" ]]; then
  echo "install.py not found at expected path: ${{INSTALL_PY}}" >&2
  exit 1
fi

"${{PYTHON_CMD}}" "${{INSTALL_PY}}" "$@"
"""


def _install_ps1(archive_name: str, extracted_dir: str) -> str:
    return f"""$ErrorActionPreference = 'Stop'
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$InstallArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundleRoot = Split-Path -Parent $scriptDir
$artifactDir = Join-Path $bundleRoot "artifacts"
$archivePath = Join-Path $artifactDir "{archive_name}"
$sumsPath = Join-Path $artifactDir "SHA256SUMS.txt"

if (-not (Test-Path $archivePath)) {{
  throw "Missing archive: $archivePath"
}}

$expected = $null
Get-Content $sumsPath | ForEach-Object {{
  $parts = ($_ -split '\\s+')
  if ($parts.Length -ge 2) {{
    $candidate = $parts[$parts.Length - 1].TrimStart('*')
    if ($candidate -eq [IO.Path]::GetFileName($archivePath)) {{
      $expected = $parts[0].ToLowerInvariant()
    }}
  }}
}}
if (-not $expected) {{
  throw "SHA256SUMS entry not found for $archivePath"
}}

$actual = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {{
  throw "Checksum mismatch for $archivePath`nexpected=$expected`nactual=$actual"
}}

$tmpDir = Join-Path $bundleRoot "_tmp_install"
if (Test-Path $tmpDir) {{
  Remove-Item -Recurse -Force $tmpDir
}}
New-Item -ItemType Directory -Path $tmpDir | Out-Null
Expand-Archive -Path $archivePath -DestinationPath $tmpDir -Force

$extractedRoot = Join-Path $tmpDir "{extracted_dir}"
$installPy = Join-Path $extractedRoot "install.py"
if (-not (Test-Path $installPy)) {{
  throw "install.py not found at expected path: $installPy"
}}

& python $installPy @InstallArgs
if ($LASTEXITCODE -ne 0) {{
  exit $LASTEXITCODE
}}
"""


def _bundle_readme(bundle_name: str, version: str, zip_name: str, tar_name: str) -> str:
    return f"""# {bundle_name}

Customer install bundle for governance release `{version}`.

## Contents

- `artifacts/{zip_name}`
- `artifacts/{tar_name}`
- `artifacts/SHA256SUMS.txt`
- `artifacts/verification-report.json`
- `install/install.sh`
- `install/install.ps1`
- `BUNDLE_MANIFEST.json`

## Quickstart

macOS/Linux:

```bash
bash install/install.sh --dry-run
bash install/install.sh --force
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File install/install.ps1 -- --dry-run
powershell -ExecutionPolicy Bypass -File install/install.ps1 -- --force
```

The installer wrappers verify archive checksums before extraction and then call `install.py`.
"""


def _write_zip(*, root_dir: Path, output_zip: Path, prefix: str) -> None:
    files = sorted(p for p in root_dir.rglob("*") if p.is_file())
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src in files:
            rel = src.relative_to(root_dir).as_posix()
            arc = f"{prefix}/{rel}"
            info = zipfile.ZipInfo(arc)
            info.date_time = FIXED_ZIP_DT
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if rel in {"install/install.sh", "install/install.ps1"} else 0o644
            info.external_attr = (mode & 0xFFFF) << 16
            with src.open("rb") as fsrc, zf.open(info, "w") as fdst:
                shutil.copyfileobj(fsrc, fdst)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build customer install bundle from dist artifacts.")
    parser.add_argument("--dist-dir", default="dist", help="Directory containing governance release artifacts.")
    parser.add_argument("--bundle-name", default="customer-install-bundle-v1", help="Bundle directory/zip base name.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = (repo_root / args.dist_dir).resolve()
    if not dist_dir.exists():
        raise SystemExit(f"Dist directory not found: {dist_dir}")

    version = _read_version(repo_root / "master.md")
    release_prefix = f"governance-{version}"

    release_zip = dist_dir / f"{release_prefix}.zip"
    release_tgz = dist_dir / f"{release_prefix}.tar.gz"
    sums = dist_dir / "SHA256SUMS.txt"
    verification = dist_dir / "verification-report.json"
    required = [release_zip, release_tgz, sums, verification]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required release artifacts for bundle: " + ", ".join(missing))

    sums_payload = _load_sha256sums(sums)
    _verify_artifact_checksums(artifacts=[release_zip, release_tgz], sums=sums_payload)
    _verify_report_hashes(report=verification, artifacts=[release_zip, release_tgz])

    bundle_root = dist_dir / args.bundle_name
    bundle_zip = dist_dir / f"{args.bundle_name}.zip"
    bundle_sha = dist_dir / f"{args.bundle_name}.SHA256"

    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    if bundle_zip.exists():
        bundle_zip.unlink()
    if bundle_sha.exists():
        bundle_sha.unlink()

    (bundle_root / "artifacts").mkdir(parents=True)
    (bundle_root / "install").mkdir(parents=True)

    shutil.copy2(release_zip, bundle_root / "artifacts" / release_zip.name)
    shutil.copy2(release_tgz, bundle_root / "artifacts" / release_tgz.name)
    shutil.copy2(sums, bundle_root / "artifacts" / sums.name)
    shutil.copy2(verification, bundle_root / "artifacts" / verification.name)

    readme_text = _bundle_readme(
        bundle_name=args.bundle_name,
        version=version,
        zip_name=release_zip.name,
        tar_name=release_tgz.name,
    )
    (bundle_root / "README.md").write_text(readme_text, encoding="utf-8")

    install_sh = bundle_root / "install" / "install.sh"
    install_ps1 = bundle_root / "install" / "install.ps1"
    install_sh.write_text(_install_sh(release_zip.name, release_prefix), encoding="utf-8")
    install_ps1.write_text(_install_ps1(release_zip.name, release_prefix), encoding="utf-8")

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "bundle_name": args.bundle_name,
        "governance_version": version,
        "release_artifacts": {
            release_zip.name: _sha256(release_zip),
            release_tgz.name: _sha256(release_tgz),
            sums.name: _sha256(sums),
            verification.name: _sha256(verification),
        },
        "installers": {
            "install/install.sh": _sha256(install_sh),
            "install/install.ps1": _sha256(install_ps1),
        },
    }
    (bundle_root / "BUNDLE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    _write_zip(root_dir=bundle_root, output_zip=bundle_zip, prefix=args.bundle_name)
    bundle_sha.write_text(f"{_sha256(bundle_zip)}  {bundle_zip.name}\n", encoding="utf-8")

    print(json.dumps(
        {
            "status": "OK",
            "bundle_dir": str(bundle_root.relative_to(repo_root)),
            "bundle_zip": str(bundle_zip.relative_to(repo_root)),
            "bundle_sha": str(bundle_sha.relative_to(repo_root)),
        },
        ensure_ascii=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
