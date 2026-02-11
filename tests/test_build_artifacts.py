from __future__ import annotations

import json
import re
import tarfile
import zipfile
from pathlib import Path

import pytest

from .util import REPO_ROOT, run_build, sha256_file, read_text


def _governance_version() -> str:
    head = "\n".join(read_text(REPO_ROOT / "master.md").splitlines()[:80])
    m = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        head,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert m, "Missing Governance-Version in master.md (required for build)"
    return m.group(1)


def _assert_member_paths_safe(names: list[str]) -> None:
    for n in names:
        assert not n.startswith("/"), f"Absolute path in archive member: {n}"
        parts = Path(n).parts
        assert ".." not in parts, f"Path traversal in archive member: {n}"


@pytest.mark.build
def test_build_is_deterministic(tmp_path: Path):
    ver = _governance_version()
    prefix = f"governance-{ver}"
    d1 = tmp_path / "dist1"
    d2 = tmp_path / "dist2"

    r = run_build(["--out-dir", str(d1), "--formats", "zip,tar.gz"])
    assert r.returncode == 0, f"build failed:\n{r.stderr}\n{r.stdout}"
    r = run_build(["--out-dir", str(d2), "--formats", "zip,tar.gz"])
    assert r.returncode == 0, f"build failed:\n{r.stderr}\n{r.stdout}"

    a1_zip = d1 / f"{prefix}.zip"
    a2_zip = d2 / f"{prefix}.zip"
    a1_tgz = d1 / f"{prefix}.tar.gz"
    a2_tgz = d2 / f"{prefix}.tar.gz"
    a1_report = d1 / "verification-report.json"
    a2_report = d2 / "verification-report.json"

    for p in [a1_zip, a2_zip, a1_tgz, a2_tgz, a1_report, a2_report]:
        assert p.exists(), f"Missing artifact: {p}"

    assert sha256_file(a1_zip) == sha256_file(a2_zip), "ZIP artifact is not deterministic across builds"
    assert sha256_file(a1_tgz) == sha256_file(a2_tgz), "TAR.GZ artifact is not deterministic across builds"
    assert sha256_file(a1_report) == sha256_file(a2_report), "verification report is not deterministic"


@pytest.mark.build
def test_artifacts_contents_follow_policy(tmp_path: Path):
    ver = _governance_version()
    prefix = f"governance-{ver}"
    dist = tmp_path / "dist"
    r = run_build(["--out-dir", str(dist), "--formats", "zip,tar.gz"])
    assert r.returncode == 0, f"build failed:\n{r.stderr}\n{r.stdout}"

    zip_path = dist / f"{prefix}.zip"
    tgz_path = dist / f"{prefix}.tar.gz"
    verification_report = dist / "verification-report.json"
    assert zip_path.exists() and tgz_path.exists()
    assert verification_report.exists()

    report_payload = json.loads(verification_report.read_text(encoding="utf-8"))
    assert report_payload.get("schema") == "governance-verification-report.v1"
    assert isinstance(report_payload.get("artifact_hashes"), dict)
    assert f"{prefix}.zip" in report_payload["artifact_hashes"]
    assert f"{prefix}.tar.gz" in report_payload["artifact_hashes"]

    forbidden_segments = {
        "/.github/",
        "/tests/",
        "/scripts/",
        "/dist/",
        "/__pycache__/",
        "/.pytest_cache/",
        "/.venv/",
        "/__MACOSX/",
    }

    # -------- ZIP policy --------
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n and not n.endswith("/")]
        assert names, "ZIP contains no files"
        _assert_member_paths_safe(names)

        assert all(n.startswith(prefix + "/") for n in names), "ZIP members must be under governance-<version>/ prefix"

        for n in names:
            for seg in forbidden_segments:
                assert seg not in ("/" + n), f"Forbidden path segment {seg} found in ZIP member: {n}"
            assert "/._" not in n, f"AppleDouble ZIP entry found: {n}"
            parts = Path(n).parts
            assert "__MACOSX" not in parts, f"__MACOSX ZIP entry found: {n}"
            assert not any(part.startswith("._") for part in parts), f"AppleDouble ZIP path part found: {n}"
            assert ".DS_Store" not in parts, f".DS_Store ZIP entry found: {n}"

        required = {
            f"{prefix}/install.py",
            f"{prefix}/master.md",
            f"{prefix}/rules.md",
            f"{prefix}/start.md",
            f"{prefix}/CHANGELOG.md",
        }
        missing = [x for x in required if x not in names]
        assert not missing, f"ZIP missing required files: {missing}"

        assert any(Path(n).name.upper().startswith(("LICENSE", "LICENCE")) for n in names), "ZIP missing LICENSE* file"
        assert any(n.startswith(f"{prefix}/profiles/") for n in names), "ZIP missing profiles/ payload"
        assert any(n.startswith(f"{prefix}/diagnostics/") for n in names), "ZIP missing diagnostics/ payload"

        for zi in zf.infolist():
            if zi.is_dir():
                continue
            assert zi.date_time == (1980, 1, 1, 0, 0, 0), f"Non-deterministic ZIP timestamp for {zi.filename}: {zi.date_time}"
            mode = (zi.external_attr >> 16) & 0o777
            if zi.filename.endswith("/install.py"):
                assert mode in (0o755, 0o775, 0o777), f"install.py should be executable in ZIP, got mode {oct(mode)}"
            else:
                assert mode in (0o644, 0o664, 0o600, 0o640), f"Unexpected mode for {zi.filename}: {oct(mode)}"

    # -------- TAR.GZ policy --------
    with tarfile.open(tgz_path, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        names = [m.name for m in members]
        assert names, "TAR.GZ contains no files"
        _assert_member_paths_safe(names)
        assert all(n.startswith(prefix + "/") for n in names), "TAR members must be under governance-<version>/ prefix"

        for n in names:
            for seg in forbidden_segments:
                assert seg not in ("/" + n), f"Forbidden path segment {seg} found in TAR member: {n}"
            assert "/._" not in n, f"AppleDouble TAR entry found: {n}"
            parts = Path(n).parts
            assert "__MACOSX" not in parts, f"__MACOSX TAR entry found: {n}"
            assert not any(part.startswith("._") for part in parts), f"AppleDouble TAR path part found: {n}"
            assert ".DS_Store" not in parts, f".DS_Store TAR entry found: {n}"

        required = {
            f"{prefix}/install.py",
            f"{prefix}/master.md",
            f"{prefix}/rules.md",
            f"{prefix}/start.md",
            f"{prefix}/CHANGELOG.md",
        }
        missing = [x for x in required if x not in names]
        assert not missing, f"TAR missing required files: {missing}"

        assert any(Path(n).name.upper().startswith(("LICENSE", "LICENCE")) for n in names), "TAR missing LICENSE* file"
        assert any(n.startswith(f"{prefix}/profiles/") for n in names), "TAR missing profiles/ payload"
        assert any(n.startswith(f"{prefix}/diagnostics/") for n in names), "TAR missing diagnostics/ payload"

        for m in members:
            assert m.mtime == 0, f"Non-deterministic TAR mtime for {m.name}: {m.mtime}"
            assert m.uid == 0 and m.gid == 0, f"Non-deterministic TAR uid/gid for {m.name}: {m.uid}/{m.gid}"
            if m.name.endswith("/install.py"):
                assert m.mode == 0o755, f"install.py should be 0755 in TAR, got {oct(m.mode)}"
            else:
                assert m.mode == 0o644, f"Unexpected mode for {m.name}: {oct(m.mode)}"
