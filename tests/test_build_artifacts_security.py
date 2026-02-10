from __future__ import annotations

import re
import shutil
import tarfile
import uuid
import zipfile
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text, run_build, sha256_file


def _governance_version() -> str:
    head = "\n".join(read_text(REPO_ROOT / "master.md").splitlines()[:80])
    m = re.search(
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        head,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert m, "Missing Governance-Version in master.md"
    return m.group(1)


_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _assert_no_traversal_or_abs(names: list[str]) -> None:
    for n in names:
        assert n, "Empty archive member name"
        assert "\\" not in n, f"Backslash in archive member: {n}"
        assert not n.startswith("/"), f"Absolute path in archive member: {n}"
        assert not n.startswith("//"), f"UNC-like path in archive member: {n}"
        assert not n.startswith("\\\\"), f"UNC-like path in archive member: {n}"
        assert not _DRIVE_RE.match(n), f"Windows drive absolute path in archive member: {n}"
        parts = Path(n).parts
        assert ".." not in parts, f"Path traversal '..' in archive member: {n}"


def _top_level_prefix(names: list[str]) -> set[str]:
    out = set()
    for n in names:
        if not n:
            continue
        out.add(n.split("/", 1)[0])
    return out


@pytest.fixture()
def built_artifacts(tmp_path: Path):
    """
    Build into a repo-relative out-dir (scripts/build.py treats --out-dir relative to repo root).
    Cleanup after.
    """
    ver = _governance_version()
    prefix = f"governance-{ver}"
    out_dir = Path(f".tmp_dist_{uuid.uuid4().hex[:8]}")
    dist_dir = REPO_ROOT / out_dir

    try:
        r = run_build(["--out-dir", out_dir.as_posix(), "--formats", "zip,tar.gz"])
        assert r.returncode == 0, f"build failed:\n{r.stderr}\n{r.stdout}"

        zip_path = dist_dir / f"{prefix}.zip"
        tgz_path = dist_dir / f"{prefix}.tar.gz"
        sums = dist_dir / "SHA256SUMS.txt"

        assert zip_path.exists(), f"Missing: {zip_path}"
        assert tgz_path.exists(), f"Missing: {tgz_path}"
        assert sums.exists(), f"Missing: {sums}"

        yield (prefix, zip_path, tgz_path, sums)
    finally:
        shutil.rmtree(dist_dir, ignore_errors=True)


@pytest.mark.build
def test_build_is_deterministic(tmp_path: Path):
    ver = _governance_version()
    prefix = f"governance-{ver}"

    # build 1
    out1 = Path(f".tmp_dist_det_{uuid.uuid4().hex[:8]}_1")
    d1 = REPO_ROOT / out1
    # build 2
    out2 = Path(f".tmp_dist_det_{uuid.uuid4().hex[:8]}_2")
    d2 = REPO_ROOT / out2

    try:
        r = run_build(["--out-dir", out1.as_posix(), "--formats", "zip,tar.gz"])
        assert r.returncode == 0, f"build1 failed:\n{r.stderr}\n{r.stdout}"
        z1 = d1 / f"{prefix}.zip"
        t1 = d1 / f"{prefix}.tar.gz"
        assert z1.exists() and t1.exists()

        r = run_build(["--out-dir", out2.as_posix(), "--formats", "zip,tar.gz"])
        assert r.returncode == 0, f"build2 failed:\n{r.stderr}\n{r.stdout}"
        z2 = d2 / f"{prefix}.zip"
        t2 = d2 / f"{prefix}.tar.gz"
        assert z2.exists() and t2.exists()

        assert sha256_file(z1) == sha256_file(z2), "ZIP not deterministic (hash differs)"
        assert sha256_file(t1) == sha256_file(t2), "TAR.GZ not deterministic (hash differs)"
    finally:
        shutil.rmtree(d1, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)


@pytest.mark.build
def test_release_archives_layout_and_contents_policy(built_artifacts):
    prefix, zip_path, tgz_path, _sums = built_artifacts

    required_rel = {
        "install.py",
        "master.md",
        "rules.md",
        "start.md",
        "profiles/addons/docsGovernance.addon.yml",
        "diagnostics/persist_workspace_artifacts.py",
        "diagnostics/bootstrap_session_state.py",
        "diagnostics/error_logs.py",
        "diagnostics/map_audit_to_canonical.py",
        "diagnostics/AUDIT_REASON_CANONICAL_MAP.json",
        "diagnostics/tool_requirements.json",
    }

    allowed_suffixes = {".md", ".json"}

    def assert_policy(members: list[str], label: str):
        files = [m for m in members if m and not m.endswith("/")]
        assert files, f"{label}: archive has no files"

        # one top-level folder only
        tops = _top_level_prefix(files)
        assert tops == {prefix}, f"{label}: expected single top-level prefix {prefix!r}, got {sorted(tops)}"
        assert all(p.startswith(prefix + "/") for p in files), f"{label}: some members not under prefix/"

        # required files exist
        missing = [f"{prefix}/{r}" for r in sorted(required_rel) if f"{prefix}/{r}" not in files]
        assert not missing, f"{label}: missing required files: {missing}"

        # must include at least one LICENSE*
        assert any(Path(n).name.upper().startswith(("LICENSE", "LICENCE")) for n in files), f"{label}: missing LICENSE*"

        # must NOT contain scripts/tests/dist (build allowlist + exclude dirs)
        forbidden_dirs = ("/tests/", "/scripts/", "/dist/", "/.github/", "/.git/")
        bad = [n for n in files if any(d in n for d in forbidden_dirs)]
        assert not bad, f"{label}: forbidden paths included: {bad[:25]}"

        # allowlist file types:
        # - install.py
        # - LICENSE*
        # - *.md + *.json
        # - profiles/addons/*.addon.yml
        # - diagnostics/*.py runtime helpers
        for n in files:
            name = Path(n).name
            rel = n.split("/", 1)[1] if "/" in n else n
            if name == "install.py":
                continue
            if name.upper().startswith(("LICENSE", "LICENCE")):
                continue
            if rel.startswith("profiles/addons/") and name.endswith(".addon.yml"):
                continue
            if rel.startswith("diagnostics/") and Path(name).suffix.lower() == ".py":
                continue
            suf = Path(n).suffix.lower()
            assert suf in allowed_suffixes, f"{label}: forbidden file type in artifact: {n}"

        addon_manifests = [n for n in files if "/profiles/addons/" in n and n.endswith(".addon.yml")]
        assert addon_manifests, f"{label}: expected addon manifests under profiles/addons/*.addon.yml"

    with zipfile.ZipFile(zip_path, "r") as zf:
        assert_policy(zf.namelist(), "ZIP")

    with tarfile.open(tgz_path, "r:gz") as tf:
        assert_policy([m.name for m in tf.getmembers()], "TAR.GZ")


@pytest.mark.build
def test_release_archives_are_safe_from_traversal_and_links(built_artifacts):
    prefix, zip_path, tgz_path, _sums = built_artifacts

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n and not n.endswith("/")]
        _assert_no_traversal_or_abs(names)
        assert all(n.startswith(prefix + "/") for n in names)

        # no symlinks in ZIP (unix mode bits)
        for zi in zf.infolist():
            if zi.is_dir():
                continue
            mode = (zi.external_attr >> 16) & 0o170000
            assert mode != 0o120000, f"Symlink detected in ZIP: {zi.filename}"

    with tarfile.open(tgz_path, "r:gz") as tf:
        members = tf.getmembers()
        names = [m.name for m in members if m.name]
        _assert_no_traversal_or_abs(names)
        assert all(n.startswith(prefix + "/") for n in names)
        for m in members:
            assert not m.issym(), f"Symlink detected in TAR: {m.name}"
            assert not m.islnk(), f"Hardlink detected in TAR: {m.name}"
