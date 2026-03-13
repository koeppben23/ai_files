from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REASON_INVALID_CONTENT = "BUSINESS_RULES_INVALID_CONTENT"
REASON_SOURCE_VIOLATION = "BUSINESS_RULES_SOURCE_VIOLATION"
REASON_SEGMENTATION_FAILED = "BUSINESS_RULES_SEGMENTATION_FAILED"
REASON_RENDER_MISMATCH = "BUSINESS_RULES_RENDER_MISMATCH"
REASON_MISSING_REQUIRED_RULES = "BUSINESS_RULES_MISSING_REQUIRED_RULES"
REASON_COUNT_MISMATCH = "BUSINESS_RULES_COUNT_MISMATCH"
REASON_EMPTY_INVENTORY = "BUSINESS_RULES_EMPTY_INVENTORY"


_DISALLOWED_DIR_TOKENS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "artifacts",
    "writers",
    "tests",
    "test",
    "__tests__",
}
_WALK_SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
_ALLOWED_SUFFIXES = {".md", ".txt", ".rst", ".adoc"}
_DISALLOWED_FILE_TOKENS = {
    "business-rules-status",
    "repo-cache",
    "repo-map-digest",
    "workspace-memory",
    "decision-pack",
    "inventory scaffold",
    "coverage",
    "writer",
}

_RULE_MARKER_RE = re.compile(r"\b(BR-[A-Za-z0-9._-]+)\b\s*[:\-]\s*")
_RULE_HEAD_RE = re.compile(r"^\s*(BR-[A-Za-z0-9._-]+)\s*[:\-]\s*(.+?)\s*$")
_SECTION_SIGNAL_RE = re.compile(
    r"(business\s+rules|policy|policies|requirement|requirements|compliance|fachregel|fachliche\s+regel)",
    re.IGNORECASE,
)
_MODAL_VERB_RE = re.compile(
    r"\b(must|shall|required|mandatory|must\s+not|may\s+not|do\s+not|forbidden|prohibited|muss|darf\s+nicht|soll|verboten)\b",
    re.IGNORECASE,
)
_DECLARATIVE_RULE_RE = re.compile(r"\b(is|are|remain|remains)\b", re.IGNORECASE)
_PATH_FRAGMENT_RE = re.compile(r"\b[a-z0-9_./-]+\.(py|ts|tsx|js|java|go|md|yaml|yml):\d+\b", re.IGNORECASE)
_ARTIFACT_RE = re.compile(
    r"(encoding=\"utf-8\"\)|\\n\"\)|written\s+only\s+when|inventory\s+scaffold|file\]\)|file\]\s*\||\}\)|\],\s*\}\)|artifacts/|tests/)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RuleCandidate:
    text: str
    source_path: str
    line_no: int
    source_allowed: bool
    source_reason: str
    section_signal: bool


@dataclass(frozen=True)
class ValidatedRule:
    rule_id: str
    text: str
    source_path: str
    line_no: int


@dataclass(frozen=True)
class RejectedRule:
    text: str
    source_path: str
    line_no: int
    reason_code: str
    reason: str


@dataclass(frozen=True)
class ValidationReport:
    valid_rules: tuple[ValidatedRule, ...]
    invalid_rules: tuple[RejectedRule, ...]
    dropped_candidates: tuple[RejectedRule, ...]
    reason_codes: tuple[str, ...]
    source_diagnostics: tuple[str, ...]
    raw_candidate_count: int
    segmented_candidate_count: int
    valid_rule_count: int
    invalid_rule_count: int
    dropped_candidate_count: int
    is_compliant: bool
    has_invalid_rules: bool
    has_render_mismatch: bool
    has_source_violation: bool
    has_missing_required_rules: bool
    has_segmentation_failure: bool
    count_consistent: bool


def source_allowlist_decision(relative_path: str) -> tuple[bool, str]:
    lowered = relative_path.replace("\\", "/").lower()
    parts = [p for p in lowered.split("/") if p]
    if any(part in _DISALLOWED_DIR_TOKENS for part in parts[:-1]):
        return False, "disallowed-directory"
    suffix = Path(lowered).suffix
    if suffix not in _ALLOWED_SUFFIXES:
        return False, "disallowed-suffix"
    filename = parts[-1] if parts else lowered
    if any(token in filename for token in _DISALLOWED_FILE_TOKENS):
        return False, "disallowed-filename"
    return True, "allowed"


def _has_section_signal(lines: list[str], line_index: int) -> bool:
    start = max(0, line_index - 6)
    for idx in range(start, line_index + 1):
        probe = lines[idx].strip()
        if not probe:
            continue
        if probe.startswith("#") and _SECTION_SIGNAL_RE.search(probe):
            return True
    return False


def extract_candidates_from_repo(repo_root: Path) -> tuple[list[RuleCandidate], bool]:
    candidates: list[RuleCandidate] = []
    try:
        for current_root, dirs, files in os.walk(repo_root):
            dirs[:] = [d for d in dirs if d not in _WALK_SKIP_DIRS]
            root = Path(current_root)
            for filename in files:
                file_path = root / filename
                relative = str(file_path.relative_to(repo_root)).replace("\\", "/")
                source_allowed, source_reason = source_allowlist_decision(relative)
                if Path(relative).suffix.lower() not in _ALLOWED_SUFFIXES:
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue
                lines = text.splitlines()
                for line_no, raw_line in enumerate(lines, start=1):
                    if "BR-" not in raw_line:
                        continue
                    section_signal = _has_section_signal(lines, line_no - 1)
                    candidates.append(
                        RuleCandidate(
                            text=raw_line.strip(),
                            source_path=relative,
                            line_no=line_no,
                            source_allowed=source_allowed,
                            source_reason=source_reason,
                            section_signal=section_signal,
                        )
                    )
    except Exception:
        return [], False
    return candidates, True


def _segment_candidate_text(raw_text: str) -> tuple[list[str], bool]:
    text = raw_text.strip()
    if not text:
        return [], True
    marker_matches = list(_RULE_MARKER_RE.finditer(text))
    if not marker_matches:
        return [], True
    segments: list[str] = []
    for idx, match in enumerate(marker_matches):
        start = match.start()
        end = marker_matches[idx + 1].start() if idx + 1 < len(marker_matches) else len(text)
        segment = text[start:end].strip(" |;,\t")
        if segment:
            segments.append(segment)
    return segments, len(segments) == 0


def sanitize_rule(raw_rule: str) -> str:
    token = raw_rule.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    token = token.replace("\\\"", '"')
    token = re.sub(r"\s+", " ", token).strip()
    token = token.strip("`'\" ,;")
    token = re.sub(r"[\]\)\}]+$", "", token).strip()
    match = _RULE_HEAD_RE.match(token)
    if not match:
        return token
    rule_id, body = match.groups()
    body = re.sub(r"\s+", " ", body).strip(" `\"',;")
    if body.endswith("-"):
        body = body[:-1].rstrip()
    return f"{rule_id}: {body}"


def _validate_rule_text(rule_text: str) -> tuple[bool, str, str]:
    match = _RULE_HEAD_RE.match(rule_text)
    if not match:
        return False, REASON_INVALID_CONTENT, "missing deterministic BR-<id>: <rule> shape"
    _, body = match.groups()
    if _RULE_MARKER_RE.search(body):
        return False, REASON_INVALID_CONTENT, "contains multiple glued rules"
    if _ARTIFACT_RE.search(rule_text):
        return False, REASON_INVALID_CONTENT, "contains code/writer/file-reference artifacts"
    if _PATH_FRAGMENT_RE.search(rule_text):
        return False, REASON_INVALID_CONTENT, "contains file path/location artifact"
    words = [w for w in body.split() if w.strip()]
    if len(words) < 2:
        return False, REASON_INVALID_CONTENT, "rule is too short or fragmentary"
    if not (_MODAL_VERB_RE.search(body) or _DECLARATIVE_RULE_RE.search(body)):
        return False, REASON_INVALID_CONTENT, "missing standalone business-rule semantics"
    return True, "none", ""


def validate_candidates(
    *,
    candidates: Iterable[RuleCandidate],
    required_rule_ids: set[str] | None = None,
    expected_rules: bool = False,
    rendered_rules: list[str] | None = None,
) -> ValidationReport:
    candidate_list = list(candidates)
    valid_rules: list[ValidatedRule] = []
    invalid_rules: list[RejectedRule] = []
    dropped: list[RejectedRule] = []
    segmented_count = 0
    seen_valid: set[str] = set()

    for candidate in candidate_list:
        if not candidate.source_allowed or not candidate.section_signal:
            dropped.append(
                RejectedRule(
                    text=candidate.text,
                    source_path=candidate.source_path,
                    line_no=candidate.line_no,
                    reason_code=REASON_SOURCE_VIOLATION,
                    reason=(
                        "source is not allowlisted"
                        if not candidate.source_allowed
                        else "missing business-rule section signal"
                    ),
                )
            )
            continue

        segments, seg_failed = _segment_candidate_text(candidate.text)
        if seg_failed:
            dropped.append(
                RejectedRule(
                    text=candidate.text,
                    source_path=candidate.source_path,
                    line_no=candidate.line_no,
                    reason_code=REASON_SEGMENTATION_FAILED,
                    reason="candidate could not be segmented into deterministic rules",
                )
            )
            continue

        segmented_count += len(segments)
        for segment in segments:
            sanitized = sanitize_rule(segment)
            ok, reason_code, reason = _validate_rule_text(sanitized)
            if not ok:
                invalid_rules.append(
                    RejectedRule(
                        text=sanitized,
                        source_path=candidate.source_path,
                        line_no=candidate.line_no,
                        reason_code=reason_code,
                        reason=reason,
                    )
                )
                continue
            rule_id = sanitized.split(":", 1)[0].strip()
            if sanitized in seen_valid:
                continue
            seen_valid.add(sanitized)
            valid_rules.append(
                ValidatedRule(
                    rule_id=rule_id,
                    text=sanitized,
                    source_path=candidate.source_path,
                    line_no=candidate.line_no,
                )
            )

    required_missing = False
    if required_rule_ids:
        extracted_ids = {v.rule_id for v in valid_rules}
        required_missing = bool(required_rule_ids - extracted_ids)
        if required_missing:
            dropped.append(
                RejectedRule(
                    text=",".join(sorted(required_rule_ids - extracted_ids)),
                    source_path="required-rules",
                    line_no=0,
                    reason_code=REASON_MISSING_REQUIRED_RULES,
                    reason="required business rules are missing",
                )
            )

    has_empty_inventory = expected_rules and len(valid_rules) == 0
    if has_empty_inventory:
        dropped.append(
            RejectedRule(
                text="",
                source_path="inventory",
                line_no=0,
                reason_code=REASON_EMPTY_INVENTORY,
                reason="no validated business rules extracted",
            )
        )

    has_render_mismatch = False
    count_consistent = True
    if rendered_rules is not None:
        rendered_clean = [sanitize_rule(item) for item in rendered_rules if str(item).strip()]
        valid_clean = [v.text for v in valid_rules]
        has_render_mismatch = rendered_clean != valid_clean
        count_consistent = len(rendered_clean) == len(valid_clean)
        if has_render_mismatch:
            dropped.append(
                RejectedRule(
                    text="rendered inventory mismatch",
                    source_path="business-rules.md",
                    line_no=0,
                    reason_code=REASON_RENDER_MISMATCH,
                    reason="rendered output is not 1:1 with validated rules",
                )
            )
        if not count_consistent:
            dropped.append(
                RejectedRule(
                    text="rendered inventory count mismatch",
                    source_path="business-rules.md",
                    line_no=0,
                    reason_code=REASON_COUNT_MISMATCH,
                    reason="validated and rendered business-rule counts differ",
                )
            )

    reason_codes = tuple(sorted({r.reason_code for r in (*invalid_rules, *dropped)}))
    source_diagnostics = tuple(sorted({f"{r.source_path}:{r.reason_code}" for r in dropped if r.source_path}))
    has_source_violation = any(r.reason_code == REASON_SOURCE_VIOLATION for r in dropped)
    has_segmentation_failure = any(r.reason_code == REASON_SEGMENTATION_FAILED for r in dropped)
    has_invalid_rules = len(invalid_rules) > 0
    has_missing_required_rules = required_missing or any(
        r.reason_code in {REASON_MISSING_REQUIRED_RULES, REASON_EMPTY_INVENTORY} for r in dropped
    )

    has_minimum_rules = len(valid_rules) > 0 or not expected_rules

    is_compliant = (
        has_minimum_rules
        and not has_invalid_rules
        and not has_source_violation
        and not has_segmentation_failure
        and not has_missing_required_rules
        and not has_render_mismatch
        and count_consistent
    )

    return ValidationReport(
        valid_rules=tuple(valid_rules),
        invalid_rules=tuple(invalid_rules),
        dropped_candidates=tuple(dropped),
        reason_codes=reason_codes,
        source_diagnostics=source_diagnostics,
        raw_candidate_count=len(candidate_list),
        segmented_candidate_count=segmented_count,
        valid_rule_count=len(valid_rules),
        invalid_rule_count=len(invalid_rules),
        dropped_candidate_count=len(dropped),
        is_compliant=is_compliant,
        has_invalid_rules=has_invalid_rules,
        has_render_mismatch=has_render_mismatch,
        has_source_violation=has_source_violation,
        has_missing_required_rules=has_missing_required_rules,
        has_segmentation_failure=has_segmentation_failure,
        count_consistent=count_consistent,
    )


def candidates_from_inventory_lines(lines: Iterable[str]) -> list[RuleCandidate]:
    candidates: list[RuleCandidate] = []
    for idx, line in enumerate(lines, start=1):
        token = line.strip()
        if token.startswith("- ") and len(token) > 2:
            candidates.append(
                RuleCandidate(
                    text=token[2:].strip(),
                    source_path="business-rules.md",
                    line_no=idx,
                    source_allowed=True,
                    source_reason="allowlisted-inventory",
                    section_signal=True,
                )
            )
            continue
        if token.startswith("Rule:"):
            candidates.append(
                RuleCandidate(
                    text=token[len("Rule:") :].strip(),
                    source_path="business-rules.md",
                    line_no=idx,
                    source_allowed=True,
                    source_reason="allowlisted-inventory",
                    section_signal=True,
                )
            )
    return candidates


def validate_inventory_markdown(content: str, *, expected_rules: bool = True) -> ValidationReport:
    candidates = candidates_from_inventory_lines(content.splitlines())
    rendered = [c.text for c in candidates]
    return validate_candidates(candidates=candidates, expected_rules=expected_rules, rendered_rules=rendered)


def render_business_rules_scaffold(*, date: str, repo_name: str) -> str:
    """Render a placeholder scaffold inventory when no extracted rules exist.

    This is the canonical scaffold renderer — it lives in the governance engine
    module so that it is always importable regardless of PYTHONPATH layout.
    The scaffold is written when Phase 1.5 has not produced extracted rules.
    """
    return "\n".join(
        [
            f"# Business Rules Inventory \u2014 {repo_name}",
            "",
            "SchemaVersion: BRINV-1",
            "Placeholder: true",
            "Source: Phase 1.5 Business Rules Discovery",
            f"Last Updated: {date}",
            "Scope: global",
            "",
            f"## BR-001 \u2014 Inventory scaffold",
            "Status: CANDIDATE",
            "Rule: Placeholder rule scaffold generated by workspace persistence helper.",
            "Scope: global",
            "Trigger: when Phase 1.5 state indicates extracted rules but no inventory file exists",
            "Enforcement: MISSING",
            "Source: inferred",
            "Confidence: 0",
            f"Last Verified: {date}",
            "Owners: none",
            "Evidence: MISSING",
            "Tests: MISSING",
            "Conflicts: none",
            "",
        ]
    )


def render_inventory_rules(date: str, repo_name: str, valid_rules: list[str], evidence_paths: list[str], extractor_version: str) -> str:
    lines = [
        f"# Business Rules Inventory - {repo_name}",
        "",
        "SchemaVersion: BRINV-1",
        "Placeholder: false",
        "Source: Phase 1.5 Business Rules Discovery",
        f"ExtractorVersion: {extractor_version}",
        f"Last Updated: {date}",
        "Scope: global",
        "",
    ]
    for rule in valid_rules:
        marker = _RULE_HEAD_RE.match(rule)
        identifier = marker.group(1) if marker else "BR-UNKNOWN"
        lines.extend([f"## {identifier}", "Status: EXTRACTED", f"Rule: {rule}", ""])
    if evidence_paths:
        lines.append("## Evidence")
        for token in evidence_paths:
            lines.append(f"- {token}")
        lines.append("")
    return "\n".join(lines)


def extract_validated_business_rules_from_repo(repo_root: Path) -> tuple[ValidationReport, bool]:
    candidates, ok = extract_candidates_from_repo(repo_root)
    if not ok:
        return validate_candidates(candidates=[]), False
    return validate_candidates(candidates=candidates, expected_rules=False), True
