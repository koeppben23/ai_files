"""Compile free-text plan content into atomic requirement contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CompiledRequirements:
    requirements: tuple[dict[str, object], ...]
    negative_contracts: tuple[dict[str, object], ...]
    verification_seed: tuple[dict[str, object], ...]
    completion_seed: tuple[dict[str, object], ...]
    notes: tuple[str, ...]


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or "requirement"


def _lines(plan_text: str) -> list[str]:
    return [line.strip() for line in str(plan_text or "").splitlines() if line.strip()]


def _is_heading(line: str) -> bool:
    return line.startswith("#")


def _infer_methods(title: str, required: str, forbidden: str) -> list[str]:
    text = " ".join([title, required, forbidden]).lower()
    methods = {"static_verification", "behavioral_verification"}
    if any(token in text for token in ("render", "visible", "output", "surface", "next action")):
        methods.add("user_surface_verification")
    if any(token in text for token in ("flow", "gate", "decision", "implement", "review", "live")):
        methods.add("live_flow_verification")
    if any(token in text for token in ("receipt", "presentation", "decision")):
        methods.add("receipts_verification")
    return sorted(methods)


def _infer_hotspots(text: str) -> list[str]:
    tokens = [
        "governance/entrypoints/session_reader.py",
    ]
    lower = text.lower()
    if "implement" in lower:
        tokens.append("governance/entrypoints/implement_start.py")
    if "review-decision" in lower or "review decision" in lower:
        tokens.append("governance/entrypoints/review_decision_persist.py")
    if "implementation-decision" in lower or "implementation decision" in lower:
        tokens.append("governance/entrypoints/implementation_decision_persist.py")
    if "receipt" in lower:
        tokens.append("governance/receipts/match.py")
    # preserve deterministic order
    seen: set[str] = set()
    out: list[str] = []
    for item in tokens:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _atomic_candidates(plan_text: str) -> list[tuple[str, str]]:
    lines = _lines(plan_text)
    candidates: list[tuple[str, str]] = []
    for line in lines:
        if _is_heading(line):
            continue
        if line.startswith(("- ", "* ")):
            text = line[2:].strip()
        else:
            text = re.sub(r"^\d+[.)]\s+", "", line).strip()
        if not text:
            continue
        title = text
        forbidden = f"forbid state: {text} not satisfied"
        candidates.append((title, forbidden))
    return candidates


def compile_plan_to_requirements(*, plan_text: str, scope_prefix: str = "PLAN") -> CompiledRequirements:
    """Compile plan bullet points into deterministic requirement skeletons.

    This compiler is intentionally strict and deterministic: each non-empty line
    in the plan body produces one atomic contract candidate.
    """

    lines = _lines(plan_text)
    if not lines:
        return CompiledRequirements(
            requirements=(),
            negative_contracts=(),
            verification_seed=(),
            completion_seed=(),
            notes=("empty_plan_text",),
        )

    out: list[dict[str, object]] = []
    negative: list[dict[str, object]] = []
    verification_seed: list[dict[str, object]] = []
    completion_seed: list[dict[str, object]] = []
    candidates = _atomic_candidates(plan_text)
    for idx, (title, forbidden_desc) in enumerate(candidates, start=1):
        digest = hashlib.sha256(f"{scope_prefix}|{idx}|{title}".encode("utf-8")).hexdigest()[:8]
        req_id = f"R-{scope_prefix}-{idx:03d}-{digest}".upper()
        slug = _slug(title)
        required_behavior = f"Implement: {title}"
        forbidden_behavior = forbidden_desc
        methods = _infer_methods(title, required_behavior, forbidden_behavior)
        acceptance_test = f"tests/test_contract_{slug}.py::test_{slug}"
        out.append(
            {
                "id": req_id,
                "title": title,
                "criticality": "important",
                "owner_test": f"tests/test_contract_{slug}.py::test_{slug}",
                "live_proof_key": f"lp-{scope_prefix.lower()}-{idx:03d}-{slug[:20]}",
                "required_behavior": [required_behavior],
                "forbidden_behavior": [forbidden_behavior],
                "user_visible_expectation": [f"User can observe outcome for: {title}"],
                "state_expectation": [f"state evidence recorded for: {title}"],
                "code_hotspots": _infer_hotspots(title),
                "verification_methods": methods,
                "acceptance_tests": [acceptance_test],
                "done_rule": {
                    "require_all_verifications_pass": True,
                    "fail_closed_on_missing_evidence": True,
                    "fail_on_forbidden_observation": True,
                },
            }
        )
        negative.append(
            {
                "id": f"N-{req_id}",
                "requirement_id": req_id,
                "forbidden_state": forbidden_behavior,
                "verification_methods": methods,
                "acceptance_tests": [acceptance_test],
                "blocking": True,
            }
        )
        verification_seed.append(
            {
                "id": req_id,
                "static_verification": "UNVERIFIED",
                "behavioral_verification": "UNVERIFIED",
                "user_surface_verification": "UNVERIFIED",
                "live_flow_verification": "UNVERIFIED",
                "receipts_verification": "UNVERIFIED",
            }
        )
        completion_seed.append(
            {
                "id": req_id,
                "overall": "UNVERIFIED",
                "evidence_refs": [],
                "missing_evidence": ["initial-verification-pending"],
            }
        )
    return CompiledRequirements(
        requirements=tuple(out),
        negative_contracts=tuple(negative),
        verification_seed=tuple(verification_seed),
        completion_seed=tuple(completion_seed),
        notes=(),
    )
