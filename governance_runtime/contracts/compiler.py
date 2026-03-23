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


@dataclass(frozen=True)
class _Segment:
    kind: str
    text: str


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or "requirement"


def _normalize_plan_lines(plan_text: str) -> list[str]:
    lines: list[str] = []
    for raw in str(plan_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def _is_heading(line: str) -> bool:
    if line.startswith("#"):
        return True
    lower = line.lower()
    return lower in {
        "required behavior",
        "forbidden behavior",
        "user-visible expectation",
        "state expectation",
        "code hotspots",
        "verification methods",
        "acceptance tests",
        "done criteria",
    }


def _looks_like_forbidden(text: str) -> bool:
    lower = text.lower().strip()
    starts = (
        "no ",
        "never ",
        "must not ",
        "do not ",
        "don't ",
        "without ",
        "forbid ",
        "forbidden ",
    )
    return lower.startswith(starts)


def _infer_segment_kind(text: str) -> str:
    lower = text.lower()
    if _looks_like_forbidden(text):
        return "forbidden_behavior"
    if any(token in lower for token in ("render", "visible", "output", "surface", "next action")):
        return "user_visible_expectation"
    if any(token in lower for token in ("receipt", "presentation", "evidence", "state", "persist", "matrix")):
        return "state_expectation"
    if any(token in lower for token in ("gate", "flow", "command", "/continue", "review", "implement")):
        return "required_behavior"
    return "required_behavior"


def _is_governance_meta_segment(text: str) -> bool:
    lower = text.lower()
    tokens = (
        " phase ",
        " gate ",
        "decision semantics",
        "state-machine",
        "review package",
        "reason-code contract",
    )
    normalized = f" {lower} "
    return any(token in normalized for token in tokens)


def _segment_plan_text(plan_text: str) -> list[_Segment]:
    segments: list[_Segment] = []
    for line in _normalize_plan_lines(plan_text):
        if _is_heading(line):
            continue
        atoms = [part.strip() for part in line.split(";") if part.strip()]
        if not atoms:
            continue
        for atom in atoms:
            segments.append(_Segment(kind=_infer_segment_kind(atom), text=atom))
    return segments


def _infer_methods(title: str, required: str, forbidden: str, segment_kind: str) -> list[str]:
    text = " ".join([title, required, forbidden]).lower()
    methods = {"static_verification", "behavioral_verification"}
    if segment_kind == "user_visible_expectation" or any(
        token in text for token in ("render", "visible", "output", "surface", "next action")
    ):
        methods.add("user_surface_verification")
    if any(token in text for token in ("flow", "gate", "decision", "implement", "review", "live", "command")):
        methods.add("live_flow_verification")
    if segment_kind == "state_expectation" or any(
        token in text for token in ("receipt", "presentation", "decision", "evidence")
    ):
        methods.add("receipts_verification")
    return sorted(methods)


def _infer_hotspots(text: str) -> list[str]:
    tokens = [
        "governance_runtime/entrypoints/session_reader.py",
    ]
    lower = text.lower()
    if "implement" in lower:
        tokens.append("governance_runtime/entrypoints/implement_start.py")
    if "review-decision" in lower or "review decision" in lower:
        tokens.append("governance_runtime/entrypoints/review_decision_persist.py")
    if "implementation-decision" in lower or "implementation decision" in lower:
        tokens.append("governance_runtime/entrypoints/implementation_decision_persist.py")
    if "receipt" in lower:
        tokens.append("governance_runtime/receipts/match.py")
    # preserve deterministic order
    seen: set[str] = set()
    out: list[str] = []
    for item in tokens:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _build_requirement_texts(segment: _Segment) -> tuple[str, str]:
    title = segment.text
    if segment.kind == "forbidden_behavior":
        required = f"Prevent forbidden behavior: {title}"
        forbidden = title
    else:
        required = f"Implement: {title}"
        forbidden = f"forbid state: {title} not satisfied"
    return required, forbidden


def _segment_notes(segments: list[_Segment]) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for segment in segments:
        counts[segment.kind] = counts.get(segment.kind, 0) + 1
    ordered_kinds = sorted(counts.keys())
    notes = [f"segments={len(segments)}"]
    notes.extend(f"{kind}={counts[kind]}" for kind in ordered_kinds)
    return tuple(notes)


def compile_plan_to_requirements(
    *,
    plan_text: str,
    scope_prefix: str = "PLAN",
    ticket_text: str = "",
    task_text: str = "",
) -> CompiledRequirements:
    """Compile plan bullet points into deterministic requirement skeletons.

    This compiler is intentionally strict and deterministic: each non-empty line
    in the plan body produces one atomic contract candidate.
    """

    segments: list[_Segment] = []
    for source in (ticket_text, task_text, plan_text):
        for segment in _segment_plan_text(source):
            if _is_governance_meta_segment(segment.text):
                continue
            segments.append(segment)
    if not segments:
        # fail open to preserve backward compatibility for legacy plans
        segments = _segment_plan_text(plan_text)
    if not segments:
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
    for idx, segment in enumerate(segments, start=1):
        title = segment.text
        digest = hashlib.sha256(f"{scope_prefix}|{idx}|{title}".encode("utf-8")).hexdigest()[:8]
        req_id = f"R-{scope_prefix}-{idx:03d}-{digest}".upper()
        slug = _slug(title)
        required_behavior, forbidden_behavior = _build_requirement_texts(segment)
        methods = _infer_methods(title, required_behavior, forbidden_behavior, segment.kind)
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
        notes=_segment_notes(segments),
    )
