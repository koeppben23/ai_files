from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys

from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event


def test_write_jsonl_event_append_writes_multiple_lines(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "error.log.jsonl"
    write_jsonl_event(target, {"n": 1}, append=True)
    write_jsonl_event(target, {"n": 2}, append=True)

    lines = target.read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in lines]
    assert [item["n"] for item in payloads] == [1, 2]


def test_write_jsonl_event_append_concurrency_smoke(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "error.log.jsonl"

    def _write(i: int) -> None:
        write_jsonl_event(target, {"n": i}, append=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_write, range(20)))

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 20


def test_write_jsonl_event_append_multiprocess_smoke(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "error.log.jsonl"
    script = (
        "from pathlib import Path\n"
        "from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event\n"
        "target=Path(r'" + str(target).replace("\\", "\\\\") + "')\n"
        "for i in range(25):\n"
        "    write_jsonl_event(target, {'n': i}, append=True)\n"
    )
    p1 = subprocess.Popen([sys.executable, "-c", script])
    p2 = subprocess.Popen([sys.executable, "-c", script])
    assert p1.wait(timeout=10) == 0
    assert p2.wait(timeout=10) == 0

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 50
    for line in lines:
        json.loads(line)
