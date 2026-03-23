"""Deterministic token-budget guard for two-layer output details."""

from __future__ import annotations


MODE_BUDGETS = {
    "compact": 240,
    "standard": 800,
    "audit": 2400,
}

TRUNCATION_ORDER = (
    "verbose_details",
    "evidence_expansions",
    "advisory_context",
)


def _details_size(details: dict[str, str]) -> int:
    """Compute deterministic detail payload size metric."""

    return sum(len(key) + len(value) for key, value in sorted(details.items()))


def apply_token_budget(*, mode: str, details: dict[str, str]) -> dict[str, str]:
    """Trim detail sections deterministically to fit configured mode budget."""

    budget = MODE_BUDGETS.get(mode, MODE_BUDGETS["standard"])
    trimmed = dict(details)
    if _details_size(trimmed) <= budget:
        return trimmed

    for key in TRUNCATION_ORDER:
        trimmed.pop(key, None)
        if _details_size(trimmed) <= budget:
            return trimmed

    # Final deterministic fallback: keep shortest entries first.
    ordered = sorted(trimmed.items(), key=lambda kv: (len(kv[1]), kv[0]))
    kept: dict[str, str] = {}
    for key, value in ordered:
        candidate = dict(kept)
        candidate[key] = value
        if _details_size(candidate) <= budget:
            kept = candidate
    return dict(sorted(kept.items()))
