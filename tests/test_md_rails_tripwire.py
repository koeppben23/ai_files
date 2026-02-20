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
        REPO_ROOT / "continue.md",
        REPO_ROOT / "resume.md",
        REPO_ROOT / "resume_prompt.md",
        REPO_ROOT / "new_profile.md",
        REPO_ROOT / "new_addon.md",
        REPO_ROOT / "AGENTS.md",
    ]
    files.extend(sorted((REPO_ROOT / "profiles").glob("rules*.md")))

    patterns = [
        r"Policy \(this document\)",
        r"/start MUST",
        r"\bTrigger:",
        r"\bSearch order:",
        r"\bMode\s*=\s*(BLOCKED|DEGRADED|DRAFT|NORMAL)\b",
        r"\bNext\s*=\s*['\"]?BLOCKED-[A-Z-]+",
        r"\bResume pointer\b",
        r"\bRequired input\b",
        r"\bRecovery steps\b",
        r"\bMUST\s+BLOCK\b",
        r"\bMUST\s+block\b",
        r"\bMUST\s+stop\b",
        r"\bMUST\s+proceed\b",
    ]

    violations: list[str] = []
    for path in files:
        text = _strip_code_fences(path.read_text(encoding="utf-8"))
        for pattern in patterns:
            for m in re.finditer(pattern, text):
                line = text.count("\n", 0, m.start()) + 1
                violations.append(f"{path.name}:{line}: {pattern}")

    assert not violations, "MD rails tripwire detected operational markers:\n" + "\n".join(violations)
