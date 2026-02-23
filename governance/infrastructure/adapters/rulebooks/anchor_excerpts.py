from __future__ import annotations


def excerpt_for_anchor(markdown: str, anchor: str) -> str:
    marker = f"# {anchor}"
    idx = markdown.find(marker)
    if idx < 0:
        return ""
    return markdown[idx : idx + 400]
