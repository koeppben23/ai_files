from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent


def _strip_code_fences(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)
    return text


def test_md_rails_tripwire_operational_markers_absent():
    files = [
        REPO_ROOT / "master.md",
        REPO_ROOT / "rules.md",
        REPO_ROOT / "start.md",
    ]
    patterns = [
        r"Policy \(this document\)",
        r"/start MUST",
        r"\bTrigger:",
        r"\bSearch order:",
        r"\bMode\s*=",
        r"\bNext\s*=",
    ]

    violations: list[str] = []
    for path in files:
        text = _strip_code_fences(path.read_text(encoding="utf-8"))
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                line = text.count("\n", 0, m.start()) + 1
                violations.append(f"{path.name}:{line}: {pattern}")

    assert not violations, "MD rails tripwire detected operational markers:\n" + "\n".join(violations)
