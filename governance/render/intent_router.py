"""Intent routing for deterministic fast-path governance responses."""

from __future__ import annotations


def route_intent(user_text: str) -> str:
    """Map free-form user text into one deterministic intent bucket."""

    text = user_text.strip().lower()
    if not text:
        return "what_now"
    if "where" in text and "am i" in text:
        return "where_am_i"
    if "block" in text:
        return "what_blocks_me"
    if "what now" in text or "next" in text:
        return "what_now"
    return "general"
