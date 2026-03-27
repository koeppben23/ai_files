"""Compile free-text plan content into atomic requirement contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
import re
from typing import Mapping


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


@dataclass(frozen=True)
class _MachineRequirement:
    title: str
    required_behavior: str
    forbidden_behavior: str
    kind: str
    code_hotspots: tuple[str, ...]
    verification_methods: tuple[str, ...]
    acceptance_tests: tuple[str, ...]


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned[:48] or "requirement"


def _owner_test_path_fragment(*, slug: str, digest: str) -> str:
    base = slug[:36] or "requirement"
    return f"{base}-{digest.lower()}"


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


def _normalize_machine_requirements(
    machine_requirements: list[Mapping[str, object]] | None,
) -> tuple[_MachineRequirement, ...]:
    if not machine_requirements:
        return ()
    out: list[_MachineRequirement] = []
    for item in machine_requirements:
        title = str(item.get("title") or "").strip()
        required_behavior = str(item.get("required_behavior") or "").strip()
        forbidden_behavior = str(item.get("forbidden_behavior") or "").strip()
        if not title or not required_behavior or not forbidden_behavior:
            continue
        kind = str(item.get("kind") or "required_behavior").strip() or "required_behavior"
        hotspots_raw = item.get("code_hotspots")
        hotspots: list[str] = []
        if isinstance(hotspots_raw, list):
            hotspots = [str(x).strip() for x in hotspots_raw if str(x).strip()]
        methods_raw = item.get("verification_methods")
        methods: list[str] = []
        if isinstance(methods_raw, list):
            methods = [str(x).strip() for x in methods_raw if str(x).strip()]
        tests_raw = item.get("acceptance_tests")
        acceptance_tests: list[str] = []
        if isinstance(tests_raw, list):
            acceptance_tests = [str(x).strip() for x in tests_raw if str(x).strip()]
        out.append(
            _MachineRequirement(
                title=title,
                required_behavior=required_behavior,
                forbidden_behavior=forbidden_behavior,
                kind=kind,
                code_hotspots=tuple(hotspots),
                verification_methods=tuple(methods),
                acceptance_tests=tuple(acceptance_tests),
            )
        )
    return tuple(out)


def compile_plan_to_requirements(
    *,
    plan_text: str,
    scope_prefix: str = "PLAN",
    ticket_text: str = "",
    task_text: str = "",
    machine_requirements: list[Mapping[str, object]] | None = None,
    strict_source: str | None = None,
) -> CompiledRequirements:
    """Compile plan bullet points into deterministic requirement skeletons.

    This compiler is intentionally strict and deterministic: each non-empty line
    in the plan body produces one atomic contract candidate.
    """

    normalized_machine = _normalize_machine_requirements(machine_requirements)

    segments: list[_Segment] = []
    source_mode = "legacy_text"
    if normalized_machine:
        source_mode = "machine_requirements"
        for req in normalized_machine:
            segments.append(_Segment(kind=req.kind, text=req.title))
    else:
        if strict_source == "machine_requirements":
            return CompiledRequirements(
                requirements=(),
                negative_contracts=(),
                verification_seed=(),
                completion_seed=(),
                notes=("source=machine_requirements", "machine_requirements=0", "strict_source_missing"),
            )
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
        owner_fragment = _owner_test_path_fragment(slug=slug, digest=digest)
        machine_req = normalized_machine[idx - 1] if idx - 1 < len(normalized_machine) else None
        if machine_req is not None:
            required_behavior = machine_req.required_behavior
            forbidden_behavior = machine_req.forbidden_behavior
            methods = list(machine_req.verification_methods) or _infer_methods(
                title,
                required_behavior,
                forbidden_behavior,
                machine_req.kind,
            )
            hotspots = list(machine_req.code_hotspots) or _infer_hotspots(title)
            acceptance_tests = list(machine_req.acceptance_tests) or [
                f"tests/test_contract_{owner_fragment}.py::test_{owner_fragment}"
            ]
        else:
            required_behavior, forbidden_behavior = _build_requirement_texts(segment)
            methods = _infer_methods(title, required_behavior, forbidden_behavior, segment.kind)
            hotspots = _infer_hotspots(title)
            acceptance_tests = [f"tests/test_contract_{owner_fragment}.py::test_{owner_fragment}"]
        out.append(
            {
                "id": req_id,
                "title": title,
                "criticality": "important",
                "owner_test": f"tests/test_contract_{owner_fragment}.py::test_{owner_fragment}",
                "live_proof_key": f"lp-{scope_prefix.lower()}-{idx:03d}-{slug[:20]}",
                "required_behavior": [required_behavior],
                "forbidden_behavior": [forbidden_behavior],
                "user_visible_expectation": [f"User can observe outcome for: {title}"],
                "state_expectation": [f"state evidence recorded for: {title}"],
                "code_hotspots": hotspots,
                "verification_methods": methods,
                "acceptance_tests": acceptance_tests,
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
                "acceptance_tests": acceptance_tests,
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
        notes=(
            f"source={source_mode}",
            f"machine_requirements={len(normalized_machine)}",
            *_segment_notes(segments),
        ),
    )
