from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from governance.infrastructure import fs_atomic


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
