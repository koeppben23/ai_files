"""Compile free-text plan content into atomic requirement contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class CompiledRequirements:
    requirements: tuple[dict[str, object], ...]
    notes: tuple[str, ...]


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or "requirement"


def compile_plan_to_requirements(*, plan_text: str, scope_prefix: str = "PLAN") -> CompiledRequirements:
    """Compile plan bullet points into deterministic requirement skeletons.

    This compiler is intentionally strict and deterministic: each non-empty line
    in the plan body produces one atomic contract candidate.
    """

    lines = [line.strip() for line in str(plan_text or "").splitlines() if line.strip()]
    if not lines:
        return CompiledRequirements(requirements=(), notes=("empty_plan_text",))

    out: list[dict[str, object]] = []
    for idx, line in enumerate(lines, start=1):
        title = line[2:].strip() if line.startswith(("- ", "* ")) else line
        digest = hashlib.sha256(f"{scope_prefix}|{idx}|{title}".encode("utf-8")).hexdigest()[:8]
        req_id = f"R-{scope_prefix}-{idx:03d}-{digest}".upper()
        slug = _slug(title)
        out.append(
            {
                "id": req_id,
                "title": title,
                "criticality": "important",
                "owner_test": f"tests/test_contract_{slug}.py::test_{slug}",
                "live_proof_key": f"LP-{scope_prefix}-{idx:03d}",
                "required_behavior": [f"Implement: {title}"],
                "forbidden_behavior": [f"Do not skip: {title}"],
                "user_visible_expectation": [f"User can observe outcome for: {title}"],
                "state_expectation": [f"state evidence recorded for: {title}"],
                "code_hotspots": ["governance/entrypoints/session_reader.py"],
                "verification_methods": [
                    "static_verification",
                    "behavioral_verification",
                    "user_surface_verification",
                ],
                "acceptance_tests": [f"tests/test_contract_{slug}.py::test_{slug}"],
                "done_rule": {
                    "require_all_verifications_pass": True,
                    "fail_closed_on_missing_evidence": True,
                    "fail_on_forbidden_observation": True,
                },
            }
        )
    return CompiledRequirements(requirements=tuple(out), notes=())
