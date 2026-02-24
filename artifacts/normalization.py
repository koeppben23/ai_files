from typing import Tuple


def normalize_legacy_placeholder_phrasing(text: str) -> Tuple[str, bool]:
    replacements = {
        "Backfill placeholder: refresh after Phase 2 discovery.": "Seed snapshot: refresh after evidence-backed Phase 2 discovery.",
        "none (backfill placeholder)": "none (no evidence-backed digest yet)",
        "Backfill placeholder; refresh after evidence-backed Phase 2 discovery.": "Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
        "Evidence: Backfill initialization only; no fresh Phase 2 domain extraction attached": "Evidence: Bootstrap seed only; no fresh Phase 2 domain extraction attached",
        "D-001: Run Phase 1.5 (Business Rules Discovery) now?": "D-001: Apply Phase 1.5 Business Rules bootstrap policy",
        "A) Yes": "Status: automatic",
        "B) No": "Action: Auto-run lightweight Phase 1.5 bootstrap when business-rules inventory is missing.",
        "Recommendation: A (run lightweight Phase 1.5 to establish initial domain evidence)": "Policy: no questions before Phase 4; use activation intent defaults.",
        "What would change it: keep B only when operator explicitly defers business-rules discovery": "What would change it: activation intent or mode policy disables auto bootstrap.",
    }
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    return updated, updated != text
