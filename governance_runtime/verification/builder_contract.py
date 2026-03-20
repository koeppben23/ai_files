"""Builder output contract (structured-only, no marketing prose)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

_ALLOWED_KEYS = {
    "changed_files",
    "contracts_addressed",
    "tests_added",
    "contracts_unverified",
}

_BANNED_PHRASES = {
    "mostly complete",
    "essentially done",
    "large part implemented",
    "ready with follow-ups",
    "core logic is there",
    "good enough",
    "100% umgesetzt",
    "fertig",
}


@dataclass(frozen=True)
class BuilderContractResult:
    ok: bool
    errors: tuple[str, ...]


def validate_builder_result(payload: Mapping[str, object]) -> BuilderContractResult:
    errors: list[str] = []

    unknown = [key for key in payload.keys() if key not in _ALLOWED_KEYS]
    if unknown:
        errors.append(f"unknown_keys:{','.join(sorted(unknown))}")

    for key in _ALLOWED_KEYS:
        value = payload.get(key)
        if not isinstance(value, list):
            errors.append(f"{key}:must_be_list")
            continue
        for item in value:
            text = str(item or "")
            if not text.strip():
                errors.append(f"{key}:contains_empty_item")
            lower = text.lower()
            for phrase in _BANNED_PHRASES:
                if phrase in lower:
                    errors.append(f"{key}:contains_banned_phrase:{phrase}")

    return BuilderContractResult(ok=not errors, errors=tuple(errors))
