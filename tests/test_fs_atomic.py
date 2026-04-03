from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from governance_runtime.infrastructure import fs_atomic


@pytest.mark.governance
def test_atomic_write_text_writes_content_with_lf(tmp_path: Path):
    target = tmp_path / "out.txt"
    fs_atomic.atomic_write_text(target, "a\r\nb\r\n", newline_lf=True)
    assert target.read_text(encoding="utf-8") == "a\nb\n"


@pytest.mark.governance
def test_bounded_retry_retries_retryable_replace(monkeypatch: pytest.MonkeyPatch):
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(errno.EACCES, "locked")
        return "ok"

    assert fs_atomic.bounded_retry(flaky, attempts=3, backoff_ms=1) == "ok"
    assert calls["n"] == 2


@pytest.mark.governance
def test_atomic_write_removes_temp_file_when_replace_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "out.txt"

    def always_fail(*_args, **_kwargs):
        raise OSError(errno.EPERM, "replace blocked")

    monkeypatch.setattr(fs_atomic, "safe_replace_with_retries", always_fail)

    with pytest.raises(OSError):
        fs_atomic.atomic_write_text(target, "payload\n")

    leftovers = [p for p in tmp_path.glob("out.txt.*.tmp") if p.is_file()]
    assert leftovers == []


@pytest.mark.governance
def test_fsync_dir_returns_immediately_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """When _is_windows() returns True, fsync_dir() must return without calling os.open or os.fsync."""
    monkeypatch.setattr(fs_atomic, "_is_windows", lambda: True)

    open_called = {"count": 0}
    fsync_called = {"count": 0}
    original_open = os.open
    original_fsync = os.fsync

    def spy_open(*args, **kwargs):
        open_called["count"] += 1
        return original_open(*args, **kwargs)

    def spy_fsync(*args, **kwargs):
        fsync_called["count"] += 1
        return original_fsync(*args, **kwargs)

    monkeypatch.setattr(os, "open", spy_open)
    monkeypatch.setattr(os, "fsync", spy_fsync)

    fs_atomic.fsync_dir(tmp_path)

    assert open_called["count"] == 0, "os.open should not be called on Windows"
    assert fsync_called["count"] == 0, "os.fsync should not be called on Windows"


@pytest.mark.governance
@pytest.mark.skipif(os.name == "nt", reason="os.open(dir, O_RDONLY) raises PermissionError on Windows")
def test_fsync_dir_calls_fsync_on_unix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """When _is_windows() returns False, fsync_dir() must call os.open and os.fsync."""
    monkeypatch.setattr(fs_atomic, "_is_windows", lambda: False)

    fsync_called = {"count": 0}
    original_fsync = os.fsync

    def spy_fsync(*args, **kwargs):
        fsync_called["count"] += 1
        return original_fsync(*args, **kwargs)

    monkeypatch.setattr(os, "fsync", spy_fsync)

    fs_atomic.fsync_dir(tmp_path)

    assert fsync_called["count"] == 1, "os.fsync should be called once on Unix"


@pytest.mark.governance
@pytest.mark.skipif(os.name == "nt", reason="tmp_path is C:\\... on Windows — test is POSIX-only")
def test_platform_path_never_adds_unc_prefix_to_posix_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Even if _is_windows() returns True, POSIX paths (starting with /) must not get \\\\?\\ prefix."""
    monkeypatch.setattr(fs_atomic, "_is_windows", lambda: True)
    result = fs_atomic._platform_path(tmp_path)
    assert not result.startswith("\\\\"), f"POSIX path got UNC prefix: {result}"
    assert result == os.path.abspath(str(tmp_path))


@pytest.mark.governance
@pytest.mark.skipif(os.name != "nt", reason="Windows-only: verifies UNC long-path prefix on real Windows paths")
def test_platform_path_adds_unc_prefix_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """On real Windows, _platform_path adds the \\\\?\\ long-path prefix."""
    monkeypatch.setattr(fs_atomic, "_is_windows", lambda: True)
    result = fs_atomic._platform_path(tmp_path)
    assert result.startswith("\\\\?\\"), f"Expected UNC prefix, got: {result}"
