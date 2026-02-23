from typing import Tuple


def normalize_legacy_placeholder_phrasing(text: str) -> Tuple[str, bool]:
    replacements = {
        "Backfill placeholder: refresh after Phase 2 discovery.": "Seed snapshot: refresh after evidence-backed Phase 2 discovery.",
        "none (backfill placeholder)": "none (no evidence-backed digest yet)",
        "Backfill placeholder; refresh after evidence-backed Phase 2 discovery.": "Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
        "Evidence: Backfill initialization only; no fresh Phase 2 domain extraction attached": "Evidence: Bootstrap seed only; no fresh Phase 2 domain extraction attached",
    }
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    return updated, updated != text
