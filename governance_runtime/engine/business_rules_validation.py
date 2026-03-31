from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from governance_runtime.engine.business_rules_code_extraction import (
    extract_code_rule_candidates_with_diagnostics,
    discover_code_surfaces,
)
from governance_runtime.engine.business_rules_coverage import (
    RC_CODE_COVERAGE_INSUFFICIENT,
    RC_CODE_EXTRACTION_NOT_RUN,
    RC_CODE_TEMPLATE_OVERFIT,
    RC_CODE_TOKEN_ARTIFACT_SPIKE,
    coverage_to_payload,
    evaluate_code_extraction_coverage,
    reconcile_code_extraction_coverage,
)


REASON_INVALID_CONTENT = "BUSINESS_RULES_INVALID_CONTENT"
REASON_SOURCE_VIOLATION = "BUSINESS_RULES_SOURCE_VIOLATION"
REASON_SEGMENTATION_FAILED = "BUSINESS_RULES_SEGMENTATION_FAILED"
REASON_RENDER_MISMATCH = "BUSINESS_RULES_RENDER_MISMATCH"
REASON_MISSING_REQUIRED_RULES = "BUSINESS_RULES_MISSING_REQUIRED_RULES"
REASON_COUNT_MISMATCH = "BUSINESS_RULES_COUNT_MISMATCH"
REASON_EMPTY_INVENTORY = "BUSINESS_RULES_EMPTY_INVENTORY"
REASON_CODE_CANDIDATE_REJECTED = "BUSINESS_RULES_CODE_CANDIDATE_REJECTED"
REASON_CODE_DOC_CONFLICT = "BUSINESS_RULES_CODE_DOC_CONFLICT"
REASON_CODE_TOKEN_ARTIFACT = "BUSINESS_RULES_CODE_TOKEN_ARTIFACT"
REASON_CODE_QUALITY_INSUFFICIENT = "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT"
REASON_CODE_TEMPLATE_OVERFIT = "BUSINESS_RULES_CODE_TEMPLATE_OVERFIT"
REASON_NON_BUSINESS_SUBJECT = "BUSINESS_RULES_NON_BUSINESS_SUBJECT"
REASON_SCHEMA_ONLY_RULE = "BUSINESS_RULES_SCHEMA_ONLY_RULE"
REASON_NON_EXECUTABLE_EVIDENCE = "BUSINESS_RULES_NON_EXECUTABLE_EVIDENCE"
REASON_GOVERNANCE_META_RULE = "BUSINESS_RULES_GOVERNANCE_META_RULE"

ORIGIN_DOC = "doc"
ORIGIN_CODE = "code"

_GOVERNANCE_META_PATTERNS = [
    r"phase_api\.yaml$",
    r"reason_codes\.registry\.json$",
    r"SESSION_STATE_SCHEMA\.md$",
    r"governance.*\.yaml$",
    r"governance.*\.json$",
    r"governance.*\.md$",
    r"\.governance/",
    r"/governance/",
    r"\.governance$",
    r"governance/validators?\.py$",
    r"governance/.*rules.*\.py$",
    r"phase[_-]?api",
    r"reason[_-]?code",
    r"session[_-]?state",
    r"registry\.json$",
    r"policy\.yaml$",
    r"rules\.yaml$",
    r"schema\.yaml$",
    r"phase[_-]?api\.yaml$",
]

_GOVERNANCE_META_SUBJECTS = {
    "session_state",
    "payload",
    "field",
    "rule",
    "phase",
    "reason_code",
    "schema",
    "recovery",
    "gate",
}


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
_CODE_TOKEN_HINT_RE = re.compile(
    r"(\bimport\b|\bdataclass\b|\bexists\b|\bresolve\b|__pycache__|_backup|\.py\b|\.ts\b|\w+_\w+_\w+)",
    re.IGNORECASE,
)
_TEMPLATE_OVERFIT_RE = re.compile(
    r"\b(required\s+field\s+checks|permission\s+checks|invariants?|schema\s+checks?)\s+must\s+be\s+enforced\s+for\s+(.+)$",
    re.IGNORECASE,
)
_GENERIC_CODE_SENTENCE_RE = re.compile(
    r"^(access\s+control\s+must\s+deny\s+unauthorized\s+operations|required\s+fields\s+must\s+be\s+validated\s+before\s+processing|disallowed\s+lifecycle\s+transitions\s+must\s+be\s+blocked|uniqueness\s+constraints\s+must\s+reject\s+duplicates|audit\s+events\s+must\s+be\s+recorded\s+for\s+protected\s+actions|retention\s+policies\s+must\s+enforce\s+archival\s+or\s+purge\s+constraints|domain\s+invariants\s+must\s+be\s+enforced\s+before\s+state\s+mutation)\.?$",
    re.IGNORECASE,
)
_TECHNICAL_TAIL_RE = re.compile(
    r"(\bfrom\b\s+\S+\s+\bimport\b|\bimport\b\s+\S+|\bdataclass\b|\b__pycache__\b|\bnode_modules\b|\bhelper\b|\bresolve\b|\bexists\b|\bmetadata\b|\bcache\b|\bfixture\b|\barchived_files\b|\brollback_plan\b|\bnot_applicable\b|[A-Za-z0-9_/.-]+\.(py|ts|tsx|js|go|java|kt|yaml|yml|json)\b|[a-z]+(?:_[a-z0-9]+){2,})",
    re.IGNORECASE,
)
_DOMAIN_WORD_RE = re.compile(
    r"\b(customer|invoice|payment|order|account|access|permission|audit|approval|transition|status|retention|policy|record|request|user|release|deploy|data)\b",
    re.IGNORECASE,
)
_VALID_CODE_SEMANTIC_TYPES = frozenset({
    "permission",
    "required-field",
    "transition",
    "uniqueness",
    "audit",
    "retention",
    "invariant",
})


@dataclass(frozen=True)
class RuleCandidate:
    text: str
    source_path: str
    line_no: int
    source_allowed: bool
    source_reason: str
    section_signal: bool
    origin: str = ORIGIN_DOC
    enforcement_anchor_type: str = ""
    semantic_type: str = ""
    evidence_kind: str = ""


@dataclass(frozen=True)
class ValidatedRule:
    rule_id: str
    text: str
    source_path: str
    line_no: int
    origin: str = ORIGIN_DOC


@dataclass(frozen=True)
class RejectedRule:
    text: str
    source_path: str
    line_no: int
    reason_code: str
    reason: str
    origin: str = ORIGIN_DOC


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
    has_code_extraction: bool = False
    code_extraction_sufficient: bool = False
    code_candidate_count: int = 0
    code_valid_rule_count: int = 0
    code_surface_count: int = 0
    missing_code_surfaces: tuple[str, ...] = ()
    has_code_coverage_gap: bool = False
    has_code_doc_conflict: bool = False
    has_code_token_artifacts: bool = False
    has_quality_insufficiency: bool = False
    invalid_code_candidate_count: int = 0
    code_token_artifact_count: int = 0
    artifact_ratio_exceeded: bool = False
    artifact_ratio: float = 0.0
    template_overfit_count: int = 0


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


_RST_UNDERLINE_RE = re.compile(r"^[=\-~^\"'+`#*]{3,}\s*$")
_ADOC_HEADING_RE = re.compile(r"^={1,6}\s+\S")
_HTML_HEADING_RE = re.compile(r"<h[1-6]\b[^>]*>", re.IGNORECASE)
_BOLD_HEADING_RE = re.compile(r"^(\*{2}|_{2}).+\1\s*$")


def _is_heading_line(line: str, lines: list[str], idx: int) -> bool:
    """Return True if *line* is a heading in Markdown, RST, AsciiDoc, or HTML."""
    stripped = line.strip()
    if not stripped:
        return False
    # Markdown ATX heading
    if stripped.startswith("#"):
        return True
    # AsciiDoc heading (= Title, == Section, etc.)
    if _ADOC_HEADING_RE.match(stripped):
        return True
    # HTML heading tag
    if _HTML_HEADING_RE.search(stripped):
        return True
    # Bold/emphasized pseudo-heading (**Business Rules** or __Business Rules__)
    if _BOLD_HEADING_RE.match(stripped):
        return True
    # RST underline-style heading: the line ABOVE the underline is the title
    if _RST_UNDERLINE_RE.match(stripped) and idx > 0:
        prev = lines[idx - 1].strip()
        if prev and not _RST_UNDERLINE_RE.match(prev):
            return True
    # RST overline+title+underline: if current line is text and the next line
    # is an underline, this line is a heading
    if idx + 1 < len(lines) and _RST_UNDERLINE_RE.match(lines[idx + 1].strip()):
        return True
    return False


def _has_section_signal(lines: list[str], line_index: int) -> bool:
    start = max(0, line_index - 6)
    for idx in range(start, line_index + 1):
        probe = lines[idx].strip()
        if not probe:
            continue
        if _is_heading_line(probe, lines, idx) and _SECTION_SIGNAL_RE.search(probe):
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
                except OSError:
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
        # fail-closed: any error during repo walk/scan returns empty candidates
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


def _technical_token_ratio(text: str) -> float:
    tokens = [tok for tok in re.findall(r"[A-Za-z0-9_./-]+", text) if tok]
    if not tokens:
        return 0.0
    technical = 0
    for tok in tokens:
        if _TECHNICAL_TAIL_RE.search(tok):
            technical += 1
    return technical / len(tokens)


def _is_template_overfit(body: str) -> bool:
    match = _TEMPLATE_OVERFIT_RE.search(body)
    return bool(match)


def _validate_rule_text(rule_text: str, *, origin: str = ORIGIN_DOC, semantic_type: str = "", evidence_kind: str = "", source_path: str = "") -> tuple[bool, str, str]:
    import re  # Import at the top to avoid scoping issues
    
    # Governance/Meta rule rejection: check source path against known governance patterns
    if source_path:
        source_lower = source_path.lower()
        for pattern in _GOVERNANCE_META_PATTERNS:
            if re.search(pattern, source_lower, re.IGNORECASE):
                return False, REASON_GOVERNANCE_META_RULE, "rule originates from governance/meta source"
    
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
    if _is_template_overfit(body):
        return False, REASON_CODE_TEMPLATE_OVERFIT, "generic template over technical residue"
    
    # Check for non-executable evidence - reject code rules that aren't marked as executable
    if origin == ORIGIN_CODE and evidence_kind and evidence_kind != "executable_code":
        return False, REASON_NON_EXECUTABLE_EVIDENCE, "code rule must be backed by executable enforcement evidence"
    
    # NEW: Business domain specificity checks for code-origin rules
    passed_business_checks = True  # Assume we pass unless proven otherwise
    if origin == ORIGIN_CODE:
        semantic = str(semantic_type or "").strip().lower()
        if semantic not in _VALID_CODE_SEMANTIC_TYPES:
            return False, REASON_CODE_CANDIDATE_REJECTED, "missing or invalid semantic type for code rule"
        if not re.search(r"\b(must|shall|required|mandatory|must\s+not|is|are)\b", body, re.IGNORECASE):
            return False, REASON_INVALID_CONTENT, "code rule lacks standalone sentence semantics"
        
        rule_lower = rule_text.lower()
        
        # Check for non-business subjects (including governance/meta subjects)
        non_business_subjects = {"value", "field", "item", "data", "object", "payload", "parameter", "input", "result"}
        non_business_subjects = non_business_subjects | _GOVERNANCE_META_SUBJECTS
        
        # Check both as split words and as substrings (for underscore-separated terms)
        rule_words = set(rule_lower.replace("_", " ").split())
        rule_substring = rule_lower.replace("_", " ")
        
        if any(subject in rule_words or subject.replace("_", " ") in rule_substring for subject in non_business_subjects):
            # Additional check: if it's primarily a technical subject
            business_indicators = {"customer", "order", "payment", "invoice", "account", "user"}
            has_business_indicator = any(indicator in rule_lower for indicator in business_indicators)
            
            # For field, we require at least one business indicator to consider it business-related
            # This prevents rejecting legitimate business rules like "Customer ID must be present"
            # while still rejecting generic technical subjects like "Field is required"
            if not has_business_indicator:
                return False, REASON_NON_BUSINESS_SUBJECT, "rule concerns non-business/technical subject"
            passed_business_checks = False  # Failed the non-business subject check
        
        # Check for schema-only rules
        schema_indicators = {"required", "validator", "validate", "schema", "constraint"}
        business_indicators = {"customer", "order", "payment", "invoice", "account", "user"}
        has_schema_indicator = any(indicator in rule_lower for indicator in schema_indicators)
        has_business_indicator = any(indicator in rule_lower for indicator in business_indicators)
        
        if has_schema_indicator and not has_business_indicator:
            # Check if it's just a formal schema statement
            formal_patterns = [
                r".*must\s+validate.*",
                r".*required\s*field.*",
                r".*schema\s*constraint.*",
                r".*field.*required.*"
            ]
            if any(re.match(pattern, rule_lower) for pattern in formal_patterns):
                return False, REASON_SCHEMA_ONLY_RULE, "rule is schema-formalism without business context"
            passed_business_checks = False  # Failed the schema-only check
    
    # Note: Generic template check removed - business context is already validated above
    # Generic templates like "Access control must deny unauthorized" are valid if they pass other checks
    
    if _CODE_TOKEN_HINT_RE.search(body):
        return False, REASON_CODE_TOKEN_ARTIFACT, "contains code-token artifact instead of business semantics"
    if _technical_token_ratio(body) > 0.45:
        return False, REASON_CODE_TOKEN_ARTIFACT, "dominated by technical tokens instead of business semantics"
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
    has_code_extraction: bool = True,
    code_extraction_sufficient: bool = True,
    code_candidate_count: int = 0,
    code_surface_count: int = 0,
    missing_code_surfaces: tuple[str, ...] = (),
    has_code_doc_conflict: bool = False,
    additional_reason_codes: tuple[str, ...] = (),
    enforce_code_requirements: bool = False,
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
                    origin=candidate.origin,
                )
            )
            continue

        if candidate.origin == ORIGIN_CODE and not str(candidate.enforcement_anchor_type or "").strip():
            dropped.append(
                RejectedRule(
                    text=candidate.text,
                    source_path=candidate.source_path,
                    line_no=candidate.line_no,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason="missing enforcement anchor for code candidate",
                    origin=candidate.origin,
                )
            )
            continue
        if candidate.origin == ORIGIN_CODE and not str(candidate.semantic_type or "").strip():
            dropped.append(
                RejectedRule(
                    text=candidate.text,
                    source_path=candidate.source_path,
                    line_no=candidate.line_no,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason="missing semantic type for code candidate",
                    origin=candidate.origin,
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
                    origin=candidate.origin,
                )
            )
            continue

        segmented_count += len(segments)
        for segment in segments:
            sanitized = sanitize_rule(segment)
            ok, reason_code, reason = _validate_rule_text(
                sanitized,
                origin=candidate.origin,
                semantic_type=candidate.semantic_type,
                evidence_kind=candidate.evidence_kind,
                source_path=candidate.source_path,
            )
            if not ok:
                invalid_rules.append(
                    RejectedRule(
                        text=sanitized,
                        source_path=candidate.source_path,
                        line_no=candidate.line_no,
                        reason_code=reason_code,
                        reason=reason,
                        origin=candidate.origin,
                    )
                )
                continue
            
            # Block C: Render/Segmentation Guard
            # Only allow rules with proper business domain context into the render pipeline
            if candidate.origin == ORIGIN_CODE:
                # Check evidence_kind - must be executable_code for code-origin rules
                evidence = str(candidate.evidence_kind or "").strip().lower()
                if evidence and evidence != "executable_code":
                    dropped.append(
                        RejectedRule(
                            text=sanitized,
                            source_path=candidate.source_path,
                            line_no=candidate.line_no,
                            reason_code=REASON_NON_EXECUTABLE_EVIDENCE,
                            reason="code rule must have executable evidence for rendering",
                            origin=candidate.origin,
                        )
                    )
                    continue
                
                # Check semantic_type - must be valid business type
                semantic = str(candidate.semantic_type or "").strip().lower()
                if semantic not in _VALID_CODE_SEMANTIC_TYPES:
                    dropped.append(
                        RejectedRule(
                            text=sanitized,
                            source_path=candidate.source_path,
                            line_no=candidate.line_no,
                            reason_code=REASON_CODE_CANDIDATE_REJECTED,
                            reason="code rule must have valid business semantic type for rendering",
                            origin=candidate.origin,
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
                    origin=candidate.origin,
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
                    origin=ORIGIN_DOC,
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
                origin=ORIGIN_DOC,
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
                    origin=ORIGIN_DOC,
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
                    origin=ORIGIN_DOC,
                )
            )

    code_valid_rule_count = sum(1 for rule in valid_rules if rule.origin == ORIGIN_CODE)
    invalid_code_candidate_count = sum(1 for row in (*invalid_rules, *dropped) if row.origin == ORIGIN_CODE)
    code_token_artifact_count = sum(1 for row in invalid_rules if row.reason_code == REASON_CODE_TOKEN_ARTIFACT)
    template_overfit_count = sum(1 for row in invalid_rules if row.reason_code == REASON_CODE_TEMPLATE_OVERFIT)
    has_source_violation = any(r.reason_code == REASON_SOURCE_VIOLATION for r in dropped)
    has_segmentation_failure = any(r.reason_code == REASON_SEGMENTATION_FAILED for r in dropped)
    artifact_ratio = (code_token_artifact_count / code_candidate_count) if code_candidate_count > 0 else 0.0
    artifact_ratio_exceeded = artifact_ratio > 0.20
    severe_validation_signal = (
        has_render_mismatch
        or has_source_violation
        or has_segmentation_failure
        or (not count_consistent)
    )
    effective_code_extraction_sufficient = bool(code_extraction_sufficient) and not severe_validation_signal
    has_quality_insufficiency = (
        (has_code_extraction and code_candidate_count > 0 and code_valid_rule_count <= 0)
        or artifact_ratio_exceeded
        or template_overfit_count > 0
        or severe_validation_signal
    )
    reason_codes_set = {r.reason_code for r in (*invalid_rules, *dropped)}
    if enforce_code_requirements:
        if has_code_extraction and not effective_code_extraction_sufficient:
            reason_codes_set.add(RC_CODE_COVERAGE_INSUFFICIENT)
        if not has_code_extraction:
            reason_codes_set.add(RC_CODE_EXTRACTION_NOT_RUN)
        if has_code_doc_conflict:
            reason_codes_set.add(REASON_CODE_DOC_CONFLICT)
        if has_quality_insufficiency:
            reason_codes_set.add(REASON_CODE_QUALITY_INSUFFICIENT)
        if artifact_ratio_exceeded:
            reason_codes_set.add(RC_CODE_TOKEN_ARTIFACT_SPIKE)
        if template_overfit_count > 0:
            reason_codes_set.add(RC_CODE_TEMPLATE_OVERFIT)
    for reason in additional_reason_codes:
        if str(reason).strip():
            reason_codes_set.add(str(reason).strip())
    reason_codes = tuple(sorted(reason_codes_set))
    source_diagnostics = tuple(sorted({f"{r.source_path}:{r.reason_code}" for r in dropped if r.source_path}))
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
    if enforce_code_requirements:
        is_compliant = (
            is_compliant
            and has_code_extraction
            and effective_code_extraction_sufficient
            and not has_code_doc_conflict
            and not has_quality_insufficiency
            and not artifact_ratio_exceeded
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
        has_code_extraction=has_code_extraction,
        code_extraction_sufficient=effective_code_extraction_sufficient,
        code_candidate_count=max(code_candidate_count, 0),
        code_valid_rule_count=max(code_valid_rule_count, 0),
        code_surface_count=max(code_surface_count, 0),
        missing_code_surfaces=tuple(missing_code_surfaces),
        has_code_coverage_gap=(not effective_code_extraction_sufficient),
        has_code_doc_conflict=has_code_doc_conflict,
        has_code_token_artifacts=(code_token_artifact_count > 0 or template_overfit_count > 0),
        has_quality_insufficiency=has_quality_insufficiency,
        invalid_code_candidate_count=max(invalid_code_candidate_count, 0),
        code_token_artifact_count=max(code_token_artifact_count, 0),
        artifact_ratio_exceeded=artifact_ratio_exceeded,
        artifact_ratio=max(artifact_ratio, 0.0),
        template_overfit_count=max(template_overfit_count, 0),
    )


def candidates_from_inventory_lines(lines: Iterable[str]) -> list[RuleCandidate]:
    candidates: list[RuleCandidate] = []
    for idx, line in enumerate(lines, start=1):
        token = line.strip()
        if token.startswith("- ") and len(token) > 2:
            body = token[2:].strip()
            # Only inventory bullets that are actual BR rules are candidates.
            # Evidence bullets (path:line) must never enter segmentation/render validation.
            if not body.startswith("BR-"):
                continue
            candidates.append(
                RuleCandidate(
                    text=body,
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


def _rules_conflict(doc_rule: str, code_rule: str) -> bool:
    doc = doc_rule.lower()
    code = code_rule.lower()
    doc_optional = "optional" in doc
    code_optional = "optional" in code
    doc_strict = any(token in doc for token in ("must", "required", "mandatory", "must not", "forbidden"))
    code_strict = any(token in code for token in ("must", "required", "mandatory", "must not", "forbidden"))
    if (doc_optional and code_strict) or (code_optional and doc_strict):
        shared = set(re.findall(r"[a-z]{4,}", doc)) & set(re.findall(r"[a-z]{4,}", code))
        return len(shared) >= 1
    if ("must not" in doc or "forbidden" in doc) and ("must" in code or "required" in code):
        shared = set(re.findall(r"[a-z]{4,}", doc)) & set(re.findall(r"[a-z]{4,}", code))
        return len(shared) >= 1
    if ("must not" in code or "forbidden" in code) and ("must" in doc or "required" in doc):
        shared = set(re.findall(r"[a-z]{4,}", doc)) & set(re.findall(r"[a-z]{4,}", code))
        return len(shared) >= 1
    return False


def _has_code_doc_conflicts(valid_rules: list[ValidatedRule]) -> bool:
    docs = [rule.text for rule in valid_rules if rule.origin == ORIGIN_DOC]
    code = [rule.text for rule in valid_rules if rule.origin == ORIGIN_CODE]
    for d_rule in docs:
        for c_rule in code:
            if _rules_conflict(d_rule, c_rule):
                return True
    return False


def extract_validated_business_rules_with_diagnostics(
    repo_root: Path,
) -> tuple[ValidationReport, dict[str, object], bool]:
    doc_candidates, docs_ok = extract_candidates_from_repo(repo_root)
    scanned_surfaces = discover_code_surfaces(repo_root)
    extraction_result, code_ok = extract_code_rule_candidates_with_diagnostics(repo_root)
    code_candidates = list(extraction_result.candidates)
    semantic_type_distribution: dict[str, int] = {}
    for candidate in code_candidates:
        semantic_type_distribution[candidate.semantic_type] = semantic_type_distribution.get(candidate.semantic_type, 0) + 1

    has_provenance_gaps = any(not candidate.path or candidate.line_start <= 0 for candidate in code_candidates)
    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=scanned_surfaces,
        candidate_count=extraction_result.candidate_count,
        extraction_ran=code_ok,
        raw_candidate_count=extraction_result.raw_candidate_count,
        dropped_candidate_count=extraction_result.dropped_candidate_count,
        has_provenance_gaps=has_provenance_gaps,
        semantic_type_distribution=semantic_type_distribution,
        dropped_non_business_surface_count=extraction_result.dropped_non_business_surface_count,
        dropped_schema_only_count=extraction_result.dropped_schema_only_count,
        dropped_non_executable_normative_text_count=extraction_result.dropped_non_executable_normative_text_count,
        accepted_business_enforcement_count=extraction_result.accepted_business_enforcement_count,
    )

    # Filter doc candidates early when code extraction is available to avoid
    # known non-business/governance leakage from generic documentation files.
    filtered_doc_candidates = list(doc_candidates)
    if code_ok and code_candidates:
        filtered_doc_candidates = [
            c for c in doc_candidates if c.source_allowed and c.section_signal
        ]

    converted_code_candidates: list[RuleCandidate] = []
    for candidate in code_candidates:
        converted = RuleCandidate(
            text=sanitize_rule(candidate.text),
            source_path=candidate.path,
            line_no=candidate.line_start,
            source_allowed=True,
            source_reason="deterministic-code-extraction",
            section_signal=True,
            origin=ORIGIN_CODE,
            enforcement_anchor_type=str(getattr(candidate, "enforcement_anchor_type", "") or ""),
            semantic_type=str(getattr(candidate, "semantic_type", "") or ""),
            evidence_kind=str(getattr(candidate, "evidence_kind", "") or ""),
        )
        # Pre-validation hard gate: keep only business-ready executable rules.
        # Candidates failing this gate are already represented in discovery drop
        # diagnostics and should not leak into render/segmentation validation.
        ok, reason_code, _ = _validate_rule_text(
            converted.text,
            origin=converted.origin,
            semantic_type=converted.semantic_type,
            evidence_kind=converted.evidence_kind,
            source_path=converted.source_path,
        )
        if not ok and reason_code in {
            REASON_GOVERNANCE_META_RULE,
            REASON_NON_BUSINESS_SUBJECT,
            REASON_SCHEMA_ONLY_RULE,
            REASON_NON_EXECUTABLE_EVIDENCE,
            REASON_CODE_CANDIDATE_REJECTED,
            REASON_INVALID_CONTENT,
            REASON_CODE_TOKEN_ARTIFACT,
            REASON_CODE_TEMPLATE_OVERFIT,
        }:
            continue
        converted_code_candidates.append(converted)

    combined_candidates = [*filtered_doc_candidates, *converted_code_candidates]
    report = validate_candidates(
        candidates=combined_candidates,
        expected_rules=False,
        has_code_extraction=code_ok,
        code_extraction_sufficient=coverage.is_sufficient,
        code_candidate_count=coverage.candidate_count,
        code_surface_count=coverage.scanned_file_count,
        missing_code_surfaces=coverage.missing_expected_surfaces,
        additional_reason_codes=coverage.reason_codes,
        enforce_code_requirements=True,
    )

    has_conflicts = _has_code_doc_conflicts(list(report.valid_rules))
    if has_conflicts:
        report = validate_candidates(
            candidates=combined_candidates,
            expected_rules=False,
            has_code_extraction=code_ok,
            code_extraction_sufficient=coverage.is_sufficient,
            code_candidate_count=coverage.candidate_count,
            code_surface_count=coverage.scanned_file_count,
            missing_code_surfaces=coverage.missing_expected_surfaces,
            has_code_doc_conflict=True,
            additional_reason_codes=tuple((*coverage.reason_codes, REASON_CODE_DOC_CONFLICT)),
            enforce_code_requirements=True,
        )

    coverage = evaluate_code_extraction_coverage(
        scanned_surfaces=scanned_surfaces,
        candidate_count=extraction_result.candidate_count,
        extraction_ran=code_ok,
        raw_candidate_count=extraction_result.raw_candidate_count,
        dropped_candidate_count=extraction_result.dropped_candidate_count,
        has_provenance_gaps=has_provenance_gaps,
        validated_code_rule_count=report.code_valid_rule_count,
        invalid_code_candidate_count=report.invalid_code_candidate_count,
        code_token_artifact_count=report.code_token_artifact_count,
        semantic_type_distribution=semantic_type_distribution,
        template_overfit_count=report.template_overfit_count,
        dropped_non_business_surface_count=extraction_result.dropped_non_business_surface_count,
        dropped_schema_only_count=extraction_result.dropped_schema_only_count,
        dropped_non_executable_normative_text_count=extraction_result.dropped_non_executable_normative_text_count,
        accepted_business_enforcement_count=extraction_result.accepted_business_enforcement_count,
    )
    coverage = reconcile_code_extraction_coverage(
        coverage,
        validation_reason_codes=report.reason_codes,
    )
    report = validate_candidates(
        candidates=combined_candidates,
        expected_rules=False,
        has_code_extraction=code_ok,
        code_extraction_sufficient=coverage.is_sufficient,
        code_candidate_count=coverage.candidate_count,
        code_surface_count=coverage.scanned_file_count,
        missing_code_surfaces=coverage.missing_expected_surfaces,
        has_code_doc_conflict=has_conflicts,
        additional_reason_codes=tuple((*coverage.reason_codes, *( (REASON_CODE_DOC_CONFLICT,) if has_conflicts else ()) )),
        enforce_code_requirements=True,
    )

    code_extraction_payload = coverage_to_payload(coverage)
    code_extraction_payload["discovery_outcomes"] = [
        {
            "path": item.path,
            "language": item.language,
            "line_start": item.line_start,
            "status": item.status,
            "source_text": item.source_text,
            "evidence_snippet": item.evidence_snippet,
            "enforcement_anchor_type": item.enforcement_anchor_type,
            "semantic_type": item.semantic_type,
        }
        for item in extraction_result.outcomes
    ]
    diagnostics = {
        "code_extraction": code_extraction_payload,
        "code_candidate_count": coverage.candidate_count,
        "raw_code_candidate_count": extraction_result.raw_candidate_count,
        "dropped_code_candidate_count": extraction_result.dropped_candidate_count,
        "docs_ok": docs_ok,
        "code_extraction_ok": code_ok,
    }
    return report, diagnostics, bool(docs_ok and code_ok)


def extract_validated_business_rules_from_repo(repo_root: Path) -> tuple[ValidationReport, bool]:
    report, _, ok = extract_validated_business_rules_with_diagnostics(repo_root)
    return report, ok


# ---------------------------------------------------------------------------
# Code-candidate merge (LLM-sourced BusinessRuleCandidates → RuleCandidate)
# ---------------------------------------------------------------------------

_CODE_CANDIDATE_ID_RE = re.compile(r"^BR-C\d{3,}$")

_VALID_PATTERN_TYPES = frozenset({
    "validation-guard",
    "constraint-check",
    "policy-enforcement",
    "enum-invariant",
    "schema-constraint",
    "guard-clause",
    "config-rule",
})

_VALID_CONFIDENCE = frozenset({"high", "medium"})

_MAX_EVIDENCE_SNIPPET_LEN = 500

_PATTERN_TO_SEMANTIC = {
    "validation-guard": "required-field",
    "constraint-check": "invariant",
    "policy-enforcement": "permission",
    "enum-invariant": "transition",
    "schema-constraint": "uniqueness",
    "guard-clause": "invariant",
    "config-rule": "retention",
}


@dataclass(frozen=True)
class ProvenanceRecord:
    """Tracks whether a validated rule was found in docs, code, or both."""

    rule_text: str
    found_in_docs: bool
    found_in_code: bool
    source_paths: tuple[str, ...]


def _normalize_rule_body(rule_text: str) -> str:
    """Extract and normalize the body of a rule for deduplication.

    Given ``"BR-C001: Foo must bar"`` returns ``"foo must bar"``.
    Given ``"BR-007: Foo must bar"`` returns ``"foo must bar"``.
    """
    match = _RULE_HEAD_RE.match(rule_text)
    if match:
        _, body = match.groups()
        return re.sub(r"\s+", " ", body).strip().lower()
    return re.sub(r"\s+", " ", rule_text).strip().lower()


def merge_code_candidates(
    code_candidates: list[dict[str, object]],
    existing_doc_rules: list[ValidatedRule],
) -> tuple[list[RuleCandidate], list[RejectedRule], list[ProvenanceRecord]]:
    """Convert LLM-sourced BusinessRuleCandidates to RuleCandidates and merge with doc-extracted rules.

    Parameters
    ----------
    code_candidates:
        Raw dicts from ``SESSION_STATE.CodebaseContext.BusinessRuleCandidates``.
    existing_doc_rules:
        Already-validated rules from the deterministic doc extractor.

    Returns
    -------
    (merged_candidates, rejected, provenance)
        - ``merged_candidates``: All doc-extracted rules as RuleCandidates **plus**
          validated code-sourced candidates (deduplicated against doc rules).
        - ``rejected``: Code candidates that failed structural pre-validation.
        - ``provenance``: One entry per final rule tracking origin(s).
    """
    rejected: list[RejectedRule] = []
    provenance: list[ProvenanceRecord] = []

    # --- Build body-index from existing doc rules for dedup ----------------
    doc_body_index: dict[str, ValidatedRule] = {}
    for rule in existing_doc_rules:
        body = _normalize_rule_body(rule.text)
        if body not in doc_body_index:
            doc_body_index[body] = rule

    # --- Provenance for doc-only rules (will be updated if code dups found)
    doc_body_provenance: dict[str, list[str]] = {}
    for rule in existing_doc_rules:
        body = _normalize_rule_body(rule.text)
        if body not in doc_body_provenance:
            doc_body_provenance[body] = []
        doc_body_provenance[body].append(f"{rule.source_path}:{rule.line_no}")

    # --- Re-create doc rules as RuleCandidates (they pass through again) ---
    merged: list[RuleCandidate] = []
    for rule in existing_doc_rules:
        merged.append(
            RuleCandidate(
                text=rule.text,
                source_path=rule.source_path,
                line_no=rule.line_no,
                source_allowed=True,
                source_reason="allowlisted-doc-extraction",
                section_signal=True,
                origin=ORIGIN_DOC,
            )
        )

    # --- Process code candidates -------------------------------------------
    seen_code_bodies: set[str] = set()

    for idx, raw in enumerate(code_candidates):
        if not isinstance(raw, dict):
            rejected.append(
                RejectedRule(
                    text=repr(raw)[:200],
                    source_path="code-candidate",
                    line_no=idx,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason="candidate is not a dict",
                    origin=ORIGIN_CODE,
                )
            )
            continue

        cand_id = raw.get("id", "")
        cand_text = raw.get("candidate_rule_text", "")
        source_path = raw.get("source_path", "")
        line_range = raw.get("line_range", "")
        pattern_type = raw.get("pattern_type", "")
        confidence = raw.get("confidence", "")
        evidence_snippet = raw.get("evidence_snippet", "")

        # --- Structural pre-validation (before entering deterministic pipeline) ---
        if not isinstance(cand_id, str) or not _CODE_CANDIDATE_ID_RE.match(cand_id):
            rejected.append(
                RejectedRule(
                    text=str(cand_text)[:200],
                    source_path=str(source_path),
                    line_no=0,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason=f"invalid candidate id: {str(cand_id)[:50]}",
                    origin=ORIGIN_CODE,
                )
            )
            continue

        if not isinstance(cand_text, str) or not cand_text.strip():
            rejected.append(
                RejectedRule(
                    text=str(cand_id),
                    source_path=str(source_path),
                    line_no=0,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason="empty or non-string candidate_rule_text",
                    origin=ORIGIN_CODE,
                )
            )
            continue

        if not isinstance(source_path, str) or not source_path.strip():
            rejected.append(
                RejectedRule(
                    text=str(cand_text)[:200],
                    source_path="unknown",
                    line_no=0,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason="empty or non-string source_path",
                    origin=ORIGIN_CODE,
                )
            )
            continue

        if not isinstance(pattern_type, str) or pattern_type not in _VALID_PATTERN_TYPES:
            rejected.append(
                RejectedRule(
                    text=str(cand_text)[:200],
                    source_path=str(source_path),
                    line_no=0,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason=f"invalid pattern_type: {str(pattern_type)[:50]}",
                    origin=ORIGIN_CODE,
                )
            )
            continue

        if not isinstance(confidence, str) or confidence not in _VALID_CONFIDENCE:
            rejected.append(
                RejectedRule(
                    text=str(cand_text)[:200],
                    source_path=str(source_path),
                    line_no=0,
                    reason_code=REASON_CODE_CANDIDATE_REJECTED,
                    reason=f"invalid confidence: {str(confidence)[:50]}",
                    origin=ORIGIN_CODE,
                )
            )
            continue

        # Truncate evidence_snippet if too long (defensive)
        if isinstance(evidence_snippet, str) and len(evidence_snippet) > _MAX_EVIDENCE_SNIPPET_LEN:
            evidence_snippet = evidence_snippet[:_MAX_EVIDENCE_SNIPPET_LEN]

        # Parse line_range for line_no (take the start of the range)
        line_no = 0
        if isinstance(line_range, str) and line_range:
            parts = line_range.split("-", 1)
            try:
                line_no = int(parts[0])
            except ValueError:
                pass

        # --- Body-based deduplication against doc rules --------------------
        sanitized = sanitize_rule(str(cand_text))
        body = _normalize_rule_body(sanitized)

        if body in seen_code_bodies:
            # Already seen this body from another code candidate
            continue
        seen_code_bodies.add(body)

        if body in doc_body_index:
            # Duplicate of a doc-extracted rule — record dual provenance
            doc_rule = doc_body_index[body]
            existing_paths = doc_body_provenance.get(body, [])
            provenance.append(
                ProvenanceRecord(
                    rule_text=doc_rule.text,
                    found_in_docs=True,
                    found_in_code=True,
                    source_paths=tuple(existing_paths + [f"{source_path}:{line_no}"]),
                )
            )
            continue

        # --- Not a duplicate: add as code-sourced candidate ----------------
        merged.append(
            RuleCandidate(
                text=sanitized,
                source_path=str(source_path),
                line_no=line_no,
                source_allowed=True,
                source_reason="llm-code-extraction",
                section_signal=True,
                origin=ORIGIN_CODE,
                enforcement_anchor_type="validator",
                semantic_type=_PATTERN_TO_SEMANTIC.get(str(pattern_type), ""),
            )
        )

    # --- Build provenance for doc-only rules (no code duplicate) -----------
    for rule in existing_doc_rules:
        body = _normalize_rule_body(rule.text)
        # Skip if already recorded as dual-provenance
        if any(p.rule_text == rule.text and p.found_in_code for p in provenance):
            continue
        # Skip duplicates in doc_body_provenance (only record first occurrence)
        if any(p.rule_text == rule.text for p in provenance):
            continue
        paths = doc_body_provenance.get(body, [f"{rule.source_path}:{rule.line_no}"])
        provenance.append(
            ProvenanceRecord(
                rule_text=rule.text,
                found_in_docs=True,
                found_in_code=False,
                source_paths=tuple(paths),
            )
        )

    # --- Build provenance for code-only rules (new, not deduped) -----------
    for candidate in merged:
        if candidate.origin != ORIGIN_CODE:
            continue
        body = _normalize_rule_body(candidate.text)
        if any(_normalize_rule_body(p.rule_text) == body for p in provenance):
            continue
        provenance.append(
            ProvenanceRecord(
                rule_text=candidate.text,
                found_in_docs=False,
                found_in_code=True,
                source_paths=(f"{candidate.source_path}:{candidate.line_no}",),
            )
        )

    return merged, rejected, provenance
