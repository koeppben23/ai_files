"""Snapshot rendering layer for governance session state.

This module provides functions to render governance session snapshots
into human-readable text formats for CLI output.

Two main rendering modes:
- format_snapshot: Debug/diagnostic key-value output
- format_guided_snapshot: Guided operator-facing output with sections

The rendering functions are stateless - they take a typed Snapshot and
return formatted strings without modifying the input.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from governance_runtime.application.dto.session_state_types import Snapshot
from governance_runtime.infrastructure.number_utils import coerce_int as _coerce_int
from governance_runtime.infrastructure.number_utils import quote_if_needed as _quote_if_needed
from governance_runtime.infrastructure.text_utils import format_list as _format_list
from governance_runtime.infrastructure.text_utils import safe_str as _safe_str

# Schema constant
SNAPSHOT_SCHEMA = "governance-session-snapshot.v1"
PHASE5_DECISION_BRIEF_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "assets" / "presentation" / "phase5_decision_brief.md"
)

# Gate purpose mappings
_GATE_PURPOSES: dict[str, str] = {
    "ticket input gate": "Capture the concrete task before planning can proceed.",
    "plan record preparation gate": "Persist the approved plan record before architecture review.",
    "architecture review gate": "Run and complete internal architecture self-review.",
    "business rules validation": "Validate business-rule compliance before implementation flow.",
    "implementation internal review": "Run deterministic internal implementation review iterations.",
    "evidence presentation gate": "Present the full governance review package for final decision.",
    "workflow complete": "Governance approval is complete; implementation can start.",
    "implementation execution in progress": "Implementation work is actively running.",
    "implementation self review": "Inspect implementation quality and derive findings.",
    "implementation revision": "Apply revisions from implementation review findings.",
    "implementation verification": "Verify the revised implementation with checks.",
    "implementation presentation gate": "Present implementation evidence for final implementation decision.",
    "implementation blocked": "Execution is blocked by hard findings that must be resolved.",
    "implementation rework clarification gate": "Clarify requested implementation changes before rerun.",
    "implementation accepted": "Implementation outcome is accepted.",
    "rework clarification gate": "Clarify requested governance changes before rerouting.",
}


def _display_phase(phase: str | None) -> str:
    """Convert phase token to display name."""
    token = str(phase or "").strip()
    lower = token.lower()
    if lower == "4":
        return "Phase 4 - Ticket Intake"
    if lower.startswith("5.4"):
        return "Phase 5 - Business Rules"
    if lower.startswith("5.5"):
        return "Phase 5 - Technical Debt"
    if lower.startswith("5.6"):
        return "Phase 5 - Rollback Safety"
    if lower.startswith("5"):
        return "Phase 5 - Architecture Review"
    if lower.startswith("6"):
        return "Phase 6 - Post Flight"
    if lower.startswith("1"):
        return "Phase 1 - Bootstrap"
    return token or "unknown"


def _section(lines: list[str], title: str) -> None:
    """Add a section header to the output lines."""
    if lines:
        lines.append("")
    lines.append(title)


def _append_list(lines: list[str], prefix: str, items: list[str] | None) -> None:
    """Append a list item to the output lines."""
    if not items:
        lines.append(f"- {prefix}: none")
        return
    lines.append(f"- {prefix}:")
    for item in items:
        lines.append(f"  - {str(item)}")


def _render_current_state(snapshot: Snapshot) -> list[str]:
    """Render the current state section."""
    phase = _display_phase(snapshot.get("phase"))
    gate = str(snapshot.get("active_gate") or "none")
    purpose = _GATE_PURPOSES.get(gate.strip().lower(), "Guide the operator to the next deterministic governance step.")
    return [
        "Current state",
        f"- Phase: {phase}",
        f"- Active gate: {gate}",
        f"- Gate purpose: {purpose}",
    ]


def _render_what_now(snapshot: Snapshot) -> list[str]:
    """Render the 'what this means now' section."""
    condition = str(snapshot.get("next_gate_condition") or "none")
    return [
        "What this means now",
        f"- {condition}",
    ]


def _render_presented_review_content(snapshot: Snapshot) -> list[str]:
    """Render the presented review content section."""
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    lines: list[str] = ["Presented review content"]
    if gate == "evidence presentation gate":
        plan_body = str(snapshot.get("review_package_plan_body") or "none")
        if plan_body.strip() and plan_body.strip().lower() != "none":
            lines.append("Phase 5 decision brief")
            lines.append("")
            for raw in plan_body.splitlines():
                text = raw.rstrip()
                lines.append(text)
            lines.append("")
        else:
            lines.append("Plan brief is unavailable.")
        evidence_summary = str(snapshot.get("review_package_evidence_summary") or "").strip()
        if evidence_summary:
            lines.append(f"Evidence: {evidence_summary}")
        return lines

    if gate == "implementation presentation gate":
        lines.append(f"- Implementation review object: {snapshot.get('implementation_package_review_object') or 'none'}")
        lines.append(f"- Approved plan reference: {snapshot.get('implementation_package_plan_reference') or 'none'}")
        _append_list(lines, "Changed files / artifact summary", snapshot.get("implementation_package_changed_files"))
        _append_list(lines, "Findings fixed", snapshot.get("implementation_package_findings_fixed"))
        _append_list(lines, "Findings open", snapshot.get("implementation_package_findings_open"))
        _append_list(lines, "Verification evidence", snapshot.get("implementation_package_checks"))
        lines.append(f"- Quality verdict: {snapshot.get('implementation_package_stability') or 'unknown'}")
        lines.append("- Decision semantics:")
        lines.append("  - approve: implementation accepted")
        lines.append("  - changes_requested: implementation rework clarification")
        lines.append("  - reject: implementation blocked")
        return lines

    lines.append("- No review presentation content is active in this gate.")
    return lines


def _split_python_list_literal(text: str) -> list[str]:
    compact = text.strip()
    if not compact.startswith("[") or not compact.endswith("]"):
        return []
    inner = compact[1:-1].strip()
    if not inner:
        return []
    parts = [part.strip().strip("'\"") for part in inner.split(",")]
    return [part for part in parts if part]


def _extract_plan_objective(plan_body: str) -> str:
    lines = [line.rstrip() for line in plan_body.splitlines()]
    for idx, line in enumerate(lines):
        if line.strip().lower() == "### plan objective" and idx + 1 < len(lines):
            objective = lines[idx + 1].strip()
            if objective:
                return objective
    return ""


def _sanitize_phase5_decision_brief(plan_body: str) -> str:
    lines = [line.rstrip() for line in plan_body.splitlines()]
    objective = _extract_plan_objective(plan_body)
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        lower = stripped.lower()

        if lower.startswith("- objective signal:"):
            if objective:
                out.append(f"- Objective: {objective}")
            else:
                out.append("- Objective: Define a concrete delivery objective before approval.")
            continue
        if lower.startswith("- target-state signal:"):
            out.append("- Target state: Define the expected end state and approval boundary.")
            continue
        if lower.startswith("- go/no-go signal:"):
            out.append("- Go/No-Go: Define explicit release gate criteria before approval.")
            continue

        risk_bullet_match = re.match(r"^-\s*(\[.*\])\s*$", stripped)
        if risk_bullet_match:
            items = _split_python_list_literal(risk_bullet_match.group(1))
            if items:
                for item in items:
                    out.append(f"- {item}")
                continue

        out.append(raw)
    return "\n".join(out).rstrip()


def _load_phase5_decision_brief_template() -> str:
    try:
        template = PHASE5_DECISION_BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8")
        if template.strip():
            return template
    except Exception:
        pass
    return (
        "# {title}\n"
        "{plan_status_badge}\n\n"
        "## Decision Required\n"
        "{decision_required}\n\n"
        "## Recommendation\n"
        "Recommendation: {recommendation}\n"
        "{recommendation_reasons}\n\n"
        "## Executive Summary\n"
        "{executive_summary}\n\n"
        "## Scope\n"
        "{scope}\n\n"
        "## Risks & Mitigations (Plain Language)\n"
        "{risks_and_mitigations}\n\n"
        "## Release Gates\n"
        "{release_gates}\n\n"
        "## Next Actions\n"
        "{next_actions}\n\n"
        "## Technical Appendix\n"
        "{technical_appendix}\n"
    )


def _extract_markdown_section(plan_body: str, heading: str) -> str:
    lines = [line.rstrip("\n") for line in plan_body.splitlines()]
    marker = f"## {heading}".lower()
    start = -1
    for idx, line in enumerate(lines):
        if line.strip().lower() == marker:
            start = idx + 1
            break
    if start == -1:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def _first_non_empty_line_after_title(plan_body: str) -> str:
    lines = [line.strip() for line in plan_body.splitlines()]
    seen_title = False
    for line in lines:
        if not line:
            continue
        if not seen_title and line.startswith("# "):
            seen_title = True
            continue
        if seen_title:
            return line
    return ""


def _render_phase5_decision_brief_from_plan_body(plan_body: str) -> str:
    sanitized = _sanitize_phase5_decision_brief(plan_body)
    title = "PHASE 5 · PLAN FOR APPROVAL"
    for line in sanitized.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip() or title
            break

    plan_status_badge = _first_non_empty_line_after_title(sanitized) or "PLAN (not implemented)"
    decision_required = _extract_markdown_section(sanitized, "Decision Required") or (
        "Decision required: choose approve, changes_requested, or reject."
    )

    recommendation_block = _extract_markdown_section(sanitized, "Recommendation")
    recommendation = "changes_requested"
    recommendation_reasons = "- Recommendation rationale is not explicitly provided."
    if recommendation_block:
        rec_lines = [line.strip() for line in recommendation_block.splitlines() if line.strip()]
        for line in rec_lines:
            if line.lower().startswith("recommendation:"):
                recommendation = line.split(":", 1)[1].strip() or recommendation
        rec_bullets = [line for line in rec_lines if line.startswith("-")]
        if rec_bullets:
            recommendation_reasons = "\n".join(rec_bullets[:3])

    executive_summary = _extract_markdown_section(sanitized, "Executive Summary")
    if not executive_summary:
        executive_summary = "- Executive summary is unavailable in this plan record."

    scope = _extract_markdown_section(sanitized, "Scope") or "Scope is not explicit enough for approval."
    risks_and_mitigations = (
        _extract_markdown_section(sanitized, "Risks & Mitigations (Plain Language)")
        or _extract_markdown_section(sanitized, "Risks & Mitigations")
        or "- No explicit risks provided."
    )
    release_gates = _extract_markdown_section(sanitized, "Release Gates") or (
        "Approval requires explicit release-gate criteria."
    )
    next_actions = _extract_markdown_section(sanitized, "Next Actions") or (
        "- /review-decision approve\n- /review-decision changes_requested\n- /review-decision reject"
    )
    technical_appendix = _extract_markdown_section(sanitized, "Technical Appendix") or "none"

    template = _load_phase5_decision_brief_template()
    try:
        rendered = template.format(
            title=title,
            plan_status_badge=plan_status_badge,
            decision_required=decision_required,
            recommendation=recommendation,
            recommendation_reasons=recommendation_reasons,
            executive_summary=executive_summary,
            scope=scope,
            risks_and_mitigations=risks_and_mitigations,
            release_gates=release_gates,
            next_actions=next_actions,
            technical_appendix=technical_appendix,
        )
        return rendered.rstrip()
    except Exception:
        return sanitized


def _render_execution_progress(snapshot: Snapshot) -> list[str]:
    """Render the execution progress section."""
    lines = ["Execution progress"]
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    if gate == "implementation internal review":
        lines.append(
            "- Internal review loop: "
            f"iteration={_coerce_int(snapshot.get('phase6_review_iterations'))}/"
            f"{_coerce_int(snapshot.get('phase6_max_review_iterations') or 3)}"
        )
        lines.append(f"- Revision delta: {snapshot.get('phase6_revision_delta') or 'changed'}")
        lines.append(f"- Decision availability: {snapshot.get('phase6_decision_availability') or 'not yet available'}")
        return lines

    if gate == "business rules validation":
        lines.append(f"- Business Rules Validation: {str(snapshot.get('p54_evaluated_status') or 'unknown').upper()}")
        lines.append(f"- Invalid rules detected: {int(snapshot.get('p54_invalid_rules') or 0)}")
        lines.append(f"- Dropped candidates: {int(snapshot.get('p54_dropped_candidates') or 0)}")
        lines.append(f"- Code candidates: {int(snapshot.get('p54_code_candidate_count') or 0)}")
        lines.append(f"- Code surfaces scanned: {int(snapshot.get('p54_code_surface_count') or 0)}")
        quality_codes = snapshot.get("p54_quality_reason_codes")
        if quality_codes:
            lines.append(f"- Reason codes: {', '.join(str(code) for code in quality_codes)}")
        return lines

    changed_files = snapshot.get("implementation_changed_files")
    if changed_files:
        _append_list(lines, "Changed files", changed_files)
    else:
        lines.append("- No file-level execution evidence is available for this gate.")

    if "implementation_execution_summary" in snapshot:
        lines.append(f"- Execution summary: {snapshot.get('implementation_execution_summary')}")
    return lines


def _has_blocker(snapshot: Snapshot) -> bool:
    """Check if the snapshot indicates a blocker."""
    status = str(snapshot.get("status") or "").strip().lower()
    if status in {"error", "blocked"}:
        return True
    gates_blocked = snapshot.get("gates_blocked")
    if gates_blocked:
        return True
    next_condition = str(snapshot.get("next_gate_condition") or "").strip().lower()
    return "blocked" in next_condition or "error" in next_condition


def _render_blocker(snapshot: Snapshot) -> list[str]:
    """Render the blocker section."""
    lines = ["Blocker"]
    lines.append(f"- Status: {snapshot.get('status') or 'unknown'}")
    lines.append(f"- Evidence: {snapshot.get('next_gate_condition') or 'No blocker detail provided.'}")
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase.startswith("5.4"):
        lines.append(
            f"- Business Rules Validation: {'FAILED' if str(snapshot.get('p54_evaluated_status')).strip().lower() != 'compliant' else 'PASSED'}"
        )
        lines.append(f"- Invalid rules detected: {int(snapshot.get('p54_invalid_rules') or 0)}")
        lines.append(f"- Dropped candidates: {int(snapshot.get('p54_dropped_candidates') or 0)}")
        reason = str(snapshot.get("p54_reason_code") or "none")
        lines.append(f"- Reason code: {reason}")
        quality_codes = snapshot.get("p54_quality_reason_codes")
        if quality_codes:
            lines.append(f"- Quality diagnostics: {', '.join(str(c) for c in quality_codes)}")
        lines.append(f"- Code extraction run: {'true' if bool(snapshot.get('p54_has_code_extraction')) else 'false'}")
        lines.append(
            f"- Code coverage sufficient: {'true' if bool(snapshot.get('p54_code_coverage_sufficient')) else 'false'}"
        )
        lines.append(f"- Code candidates: {int(snapshot.get('p54_code_candidate_count') or 0)}")
        lines.append(f"- Code surfaces scanned: {int(snapshot.get('p54_code_surface_count') or 0)}")
        missing_surfaces = snapshot.get("p54_missing_code_surfaces")
        if missing_surfaces:
            lines.append(f"- Missing code surfaces: {', '.join(str(s) for s in missing_surfaces)}")
    implementation_reasons = snapshot.get("implementation_reason_codes")
    if implementation_reasons:
        lines.append(
            f"- Implementation Validation: {'FAILED' if str(snapshot.get('active_gate')).strip().lower() == 'implementation blocked' else 'PASSED'}"
        )
        lines.append(f"- Executor invoked: {'true' if bool(snapshot.get('implementation_executor_invoked')) else 'false'}")
        lines.append(
            f"- Changed files: {len(snapshot.get('implementation_changed_files') or [])}"
        )
        lines.append(
            f"- Domain files changed: {len(snapshot.get('implementation_domain_changed_files') or [])}"
        )
        lines.append(f"- Reason codes: {', '.join(str(r) for r in implementation_reasons)}")
    gates_blocked = snapshot.get("gates_blocked")
    if gates_blocked:
        lines.append(f"- Blocked gates: {', '.join(str(g) for g in gates_blocked)}")
    return lines


def format_snapshot(snapshot: Snapshot) -> str:
    """Format debug/diagnostic key-value output (non-guided surface)."""
    lines = [f"# {SNAPSHOT_SCHEMA}"]
    for key, value in snapshot.items():
        if key == "schema":
            continue
        if isinstance(value, list):
            lines.append(f"{key}: {_format_list(value)}")
        else:
            lines.append(f"{key}: {_quote_if_needed(_safe_str(value))}")
    return "\n".join(lines) + "\n"


def render_guided_sections(snapshot: Snapshot, action_line: str, *, verbose_governance_frame: bool = False) -> list[str]:
    """Render the guided output sections based on snapshot state.

    Returns list of lines for the main body sections (not including action line).
    """
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    if gate == "evidence presentation gate" and not _has_blocker(snapshot) and not verbose_governance_frame:
        plan_body = str(snapshot.get("review_package_plan_body") or "").strip()
        if plan_body and plan_body.lower() != "none":
            rendered = _render_phase5_decision_brief_from_plan_body(plan_body)
            if rendered:
                return [line.rstrip() for line in rendered.splitlines()]
        return ["Plan brief is unavailable."]

    lines: list[str] = []
    lines.extend(_render_current_state(snapshot))
    _section(lines, "What this means now")
    lines.append(f"- {str(snapshot.get('next_gate_condition') or 'none')}")

    if _has_blocker(snapshot):
        _section(lines, "Blocker")
        lines.extend(_render_blocker(snapshot)[1:])
    elif gate in {"evidence presentation gate", "implementation presentation gate"}:
        _section(lines, "Presented review content")
        lines.extend(_render_presented_review_content(snapshot)[1:])
    else:
        _section(lines, "Execution progress")
        lines.extend(_render_execution_progress(snapshot)[1:])

    return lines


def format_guided_snapshot(
    snapshot: Snapshot,
    action_line: str | None = None,
    *,
    verbose_governance_frame: bool = False,
) -> str:
    """Format guided operator-facing output with sections.

    Args:
        snapshot: The typed snapshot to render.
        action_line: The pre-computed next action line (from presentation assembly).
                   If None, a default will be generated.
    """
    if action_line is None:
        action_line = "Next action: consult next-step."
    lines = render_guided_sections(snapshot, action_line, verbose_governance_frame=verbose_governance_frame)
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    if not (gate == "evidence presentation gate" and not _has_blocker(snapshot) and not verbose_governance_frame):
        lines.append("")
        lines.append(action_line)
    return "\n".join(lines).rstrip() + "\n"
