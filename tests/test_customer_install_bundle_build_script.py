from __future__ import annotations

import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text, run_build, run_customer_bundle_build, sha256_file


def _governance_version() -> str:
    head = "\n".join(read_text(REPO_ROOT / "master.md").splitlines()[:80])
    match = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        head,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert match, "Missing Governance-Version in master.md"
    return match.group(1)


@pytest.mark.build
def test_customer_install_bundle_build_outputs_expected_files():
    version = _governance_version()
    release_prefix = f"governance-{version}"
    out_dir = Path(f".tmp_dist_bundle_{uuid.uuid4().hex[:8]}")
    dist_dir = REPO_ROOT / out_dir

    try:
        build = run_build(["--out-dir", out_dir.as_posix(), "--formats", "zip,tar.gz"])
        assert build.returncode == 0, f"build failed:\n{build.stderr}\n{build.stdout}"

        bundle = run_customer_bundle_build(["--dist-dir", out_dir.as_posix()])
        assert bundle.returncode == 0, f"bundle build failed:\n{bundle.stderr}\n{bundle.stdout}"
        payload = json.loads(bundle.stdout)
        assert payload["status"] == "OK"

        bundle_dir = dist_dir / "customer-install-bundle-v1"
        bundle_zip = dist_dir / "customer-install-bundle-v1.zip"
        bundle_sha = dist_dir / "customer-install-bundle-v1.SHA256"
        assert bundle_dir.exists()
        assert bundle_zip.exists()
        assert bundle_sha.exists()

        required_local = [
            bundle_dir / "README.md",
            bundle_dir / "BUNDLE_MANIFEST.json",
            bundle_dir / "install" / "install.sh",
            bundle_dir / "install" / "install.ps1",
            bundle_dir / "artifacts" / f"{release_prefix}.zip",
            bundle_dir / "artifacts" / f"{release_prefix}.tar.gz",
            bundle_dir / "artifacts" / "SHA256SUMS.txt",
            bundle_dir / "artifacts" / "verification-report.json",
        ]
        missing = [str(path) for path in required_local if not path.exists()]
        assert not missing, f"Missing bundle files: {missing}"

        manifest = json.loads((bundle_dir / "BUNDLE_MANIFEST.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == "governance.customer-install-bundle.v1"
        assert manifest["governance_version"] == version
        assert f"{release_prefix}.zip" in manifest["release_artifacts"]
        assert f"{release_prefix}.tar.gz" in manifest["release_artifacts"]

        with zipfile.ZipFile(bundle_zip, "r") as zf:
            members = {name for name in zf.namelist() if name and not name.endswith("/")}
        required_members = {
            "customer-install-bundle-v1/README.md",
            "customer-install-bundle-v1/BUNDLE_MANIFEST.json",
            "customer-install-bundle-v1/install/install.sh",
            "customer-install-bundle-v1/install/install.ps1",
            f"customer-install-bundle-v1/artifacts/{release_prefix}.zip",
            f"customer-install-bundle-v1/artifacts/{release_prefix}.tar.gz",
            "customer-install-bundle-v1/artifacts/SHA256SUMS.txt",
            "customer-install-bundle-v1/artifacts/verification-report.json",
        }
        assert required_members.issubset(members)

        sha_line = bundle_sha.read_text(encoding="utf-8").strip()
        expected_sha = sha_line.split()[0]
        assert expected_sha == sha256_file(bundle_zip)
    finally:
        shutil.rmtree(dist_dir, ignore_errors=True)


@pytest.mark.build
def test_customer_install_bundle_build_is_deterministic():
    out_dir = Path(f".tmp_dist_bundle_det_{uuid.uuid4().hex[:8]}")
    dist_dir = REPO_ROOT / out_dir

    try:
        build = run_build(["--out-dir", out_dir.as_posix(), "--formats", "zip,tar.gz"])
        assert build.returncode == 0, f"build failed:\n{build.stderr}\n{build.stdout}"

        first = run_customer_bundle_build(["--dist-dir", out_dir.as_posix()])
        assert first.returncode == 0, f"first bundle build failed:\n{first.stderr}\n{first.stdout}"
        first_hash = sha256_file(dist_dir / "customer-install-bundle-v1.zip")

        second = run_customer_bundle_build(["--dist-dir", out_dir.as_posix()])
        assert second.returncode == 0, f"second bundle build failed:\n{second.stderr}\n{second.stdout}"
        second_hash = sha256_file(dist_dir / "customer-install-bundle-v1.zip")

        assert first_hash == second_hash, "customer install bundle zip is not deterministic"
    finally:
        shutil.rmtree(dist_dir, ignore_errors=True)
