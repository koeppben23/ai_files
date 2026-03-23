from __future__ import annotations


def normalize_phase_token(value: str) -> str:
    token = value.strip()
    return token if token else "1.1-Bootstrap"
