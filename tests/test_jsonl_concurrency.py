from __future__ import annotations

import json
import threading
from pathlib import Path

from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event


def test_jsonl_append_is_lock_safe_under_parallel_writers(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "events.jsonl"
    workers = 20
    per_worker = 50

    def _writer(worker_id: int) -> None:
        for idx in range(per_worker):
            write_jsonl_event(
                target,
                {"worker": worker_id, "idx": idx, "message": f"w{worker_id}-{idx}"},
                append=True,
            )

    threads = [threading.Thread(target=_writer, args=(wid,)) for wid in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == workers * per_worker
    parsed = [json.loads(line) for line in lines]
    assert all(isinstance(row, dict) for row in parsed)
