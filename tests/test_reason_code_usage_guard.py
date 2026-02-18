from __future__ import annotations

from pathlib import Path
import re

import pytest

from governance.domain import reason_codes


REPO_ROOT = Path(__file__).resolve().parents[1]
BLOCKED_LITERAL_RE = re.compile(r"\b(BLOCKED-[A-Z0-9-]+)\b")


@pytest.mark.governance
def test_blocked_reason_literals_in_governance_code_are_registered():
    registered = set(reason_codes.CANONICAL_REASON_CODES)
    seen: set[str] = set()

    for path in (REPO_ROOT / "governance").glob("**/*.py"):
        text = path.read_text(encoding="utf-8")
        seen.update(BLOCKED_LITERAL_RE.findall(text))

    unknown = sorted(code for code in seen if code not in registered)
    assert not unknown, f"unregistered BLOCKED literals found: {unknown}"
