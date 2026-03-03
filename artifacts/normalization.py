import re
from typing import Tuple


_LEGACY_DECISION_PACK_PATTERNS = (
    re.compile(r"(?im)^\s*A\)\s*Yes\s*$"),
    re.compile(r"(?im)^\s*B\)\s*No\s*$"),
)


def has_legacy_decision_pack_ab_prompt(text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in _LEGACY_DECISION_PACK_PATTERNS)


def normalize_legacy_placeholder_phrasing(text: str) -> Tuple[str, bool]:
    replacements = {
        "Backfill placeholder: refresh after Phase 2 discovery.": "Seed snapshot: refresh after evidence-backed Phase 2 discovery.",
        "none (backfill placeholder)": "none (no evidence-backed digest yet)",
        "Backfill placeholder; refresh after evidence-backed Phase 2 discovery.": "Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
        "Evidence: Backfill initialization only; no fresh Phase 2 domain extraction attached": "Evidence: Bootstrap seed only; no fresh Phase 2 domain extraction attached",
        "D-001: Run Phase 1.5 (Business Rules Discovery) now?": "D-001: Record Business Rules bootstrap outcome",
        "A) Yes": "Status: automatic",
        "B) No": "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
        "Recommendation: A (run lightweight Phase 1.5 to establish initial domain evidence)": "Policy: business-rules.md is written only when outcome is extracted.",
        "What would change it: keep B only when operator explicitly defers business-rules discovery": "What would change it: scope evidence or Phase 1.5 extraction state.",
    }
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    updated = re.sub(r"(?im)^\s*A\)\s*Yes\s*$", "Status: automatic", updated)
    updated = re.sub(
        r"(?im)^\s*B\)\s*No\s*$",
        "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
        updated,
    )
    return updated, updated != text
