from __future__ import annotations

import re

from tests.util import REPO_ROOT, get_docs_path, get_master_path, get_profiles_path, get_rules_path, get_review_path


def _strip_code_fences(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"~~~[\s\S]*?~~~", "", text)
    return text


def test_md_rails_tripwire_operational_markers_absent():
    files = [
        get_master_path(),
        get_rules_path(),
        REPO_ROOT / "opencode" / "commands" / "continue.md",
        get_review_path(),
        get_docs_path() / "resume.md",
        get_docs_path() / "resume_prompt.md",
        get_docs_path() / "new_profile.md",
        get_docs_path() / "new_addon.md",
        REPO_ROOT / "BOOTSTRAP.md",
    ]
    files.extend(sorted(get_profiles_path().glob("rules*.md")))

    patterns = [
        r"Policy \(this document\)",
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
