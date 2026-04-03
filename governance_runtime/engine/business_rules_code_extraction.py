from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


# Surface kinds
SURFACE_KIND_BUSINESS_DOMAIN_CODE = "business_domain_code"
SURFACE_KIND_META_GOVERNANCE = "meta_governance"
SURFACE_KIND_SCHEMA_CONFIG = "schema_config"
SURFACE_KIND_DOCSTRING_OR_COMMENT = "docstring_or_comment"
SURFACE_KIND_LINT_OR_STYLE = "lint_or_style"
SURFACE_KIND_INFRA_FRAMEWORK = "infra_framework"

# Additional drop statuses
DISCOVERY_DROPPED_NON_BUSINESS_SURFACE = "dropped_non_business_surface"
DISCOVERY_DROPPED_SCHEMA_ONLY = "dropped_schema_only"
DISCOVERY_DROPPED_NON_EXECUTABLE_NORMATIVE_TEXT = "dropped_non_executable_normative_text"

_CODE_SUFFIXES = {
    ".py",
    ".go",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".java",
    ".kt",
    ".sql",
    ".yaml",
    ".yml",
    ".json",
}

_SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "venv",
    ".venv",
    "tests",
    "test",
    "__tests__",
    "artifacts",
}

_ANCHOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("raise", re.compile(r"\b(raise|throw)\b", re.IGNORECASE)),
    ("assert", re.compile(r"\bassert\b", re.IGNORECASE)),
    ("deny", re.compile(r"\b(forbidden|unauthorized|permission\s*denied|deny|denied)\b", re.IGNORECASE)),
    ("return-error", re.compile(r"\breturn\b[^\n]*(error|err\b|fail|invalid|forbidden|unauthorized)", re.IGNORECASE)),
    ("validator", re.compile(r"\b(validate|validator|required|required\s*field|schema|constraint)\b", re.IGNORECASE)),
    ("transition-guard", re.compile(r"\b(transition|state\s*machine|status\s*transition|lifecycle)\b", re.IGNORECASE)),
    ("retention-enforcement", re.compile(r"\b(retention|archive|purge|ttl|soft_delete)\b", re.IGNORECASE)),
    ("audit-enforcement", re.compile(r"\b(audit|log_event|append_log|journal|audit_log)\b", re.IGNORECASE)),
)

_SEMANTIC_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("permission", "Access control must deny unauthorized operations.", re.compile(r"(permission|authorize|authz|acl|requires?_role|forbidden|unauthorized)", re.IGNORECASE)),
    ("required-field", "Required fields must be validated before processing.", re.compile(r"(required|missing|if\s+not\s+\w+|not\s+\w+|validate|required\s*=\s*true)" , re.IGNORECASE)),
    ("transition", "Disallowed lifecycle transitions must be blocked.", re.compile(r"(status|state|transition|state_machine|lifecycle)", re.IGNORECASE)),
    ("uniqueness", "Uniqueness constraints must reject duplicates.", re.compile(r"(unique|duplicate|already\s+exists|conflict)", re.IGNORECASE)),
    ("audit", "Audit events must be recorded for protected actions.", re.compile(r"(audit|log_event|append_log|journal|audit_log)", re.IGNORECASE)),
    ("retention", "Retention policies must enforce archival or purge constraints.", re.compile(r"(retention|archive|soft_delete|purge|ttl)", re.IGNORECASE)),
    ("invariant", "Domain invariants must be enforced before state mutation.", re.compile(r"(invariant|must_not|forbid|immutable|constraint)", re.IGNORECASE)),
)

_NON_NORMATIVE_LINE_RE = re.compile(
    r"^(from\s+\S+\s+import\s+\S+|import\s+\S+|@\w+|class\s+\w+\(|def\s+\w+\(|dataclass\b)",
    re.IGNORECASE,
)

_COMMENT_PREFIX_RE = re.compile(r"^\s*(#|//|/\*|\*)\s*")
_NORMATIVE_COMMENT_RE = re.compile(
    r"\b(must|shall|required|mandatory|must\s+not|forbidden|prohibited|deny|reject)\b",
    re.IGNORECASE,
)
_DISCOVERY_TECHNICAL_ARTIFACT_RE = re.compile(
    r"(from\s+\S+\s+import\s+\S+|^import\s+\S+|^@\w+|\bdataclass\b|\bfixture\b|\bcache\b|\bfrozen\s*=\s*(true|false)\b|\bslots\s*=\s*(true|false)\b|__pycache__|node_modules|\.git|artifacts?/|fixtures?/|metadata|[A-Za-z0-9_/.-]+\.(py|ts|tsx|js|jsx|go|java|kt|yaml|yml|json)(:\d+)?)",
    re.IGNORECASE,
)
_TECHNICAL_ARTIFACT_RE = re.compile(
    r"(from\s+\S+\s+import\s+\S+|^import\s+\S+|\b@dataclass\b|__pycache__|node_modules|\.git|\.pytest_cache|artifacts?/|fixtures?/|cache|backup|metadata)",
    re.IGNORECASE,
)
_PATH_FRAGMENT_RE = re.compile(r"\b\S+\.(py|ts|tsx|js|jsx|go|java|kt|yaml|yml|json)(:\d+)?\b", re.IGNORECASE)
_IDENTIFIER_CHAIN_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+){2,}\b")
_WEAK_TECHNICAL_ONLY_RE = re.compile(r"\b(exists|resolve|helper|state)\b", re.IGNORECASE)
_NAKED_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DECLARATION_LINE_RE = re.compile(r"^\s*(def|class|func|function|interface|type)\b", re.IGNORECASE)
_SEMANTIC_KEYWORD_RE = re.compile(
    r"\b(permission|unauthorized|forbidden|required|missing|validate|constraint|transition|state|status|lifecycle|unique|duplicate|audit|retention|archive|purge|ttl|invariant)\b",
    re.IGNORECASE,
)
_COMMENT_FOR_TAIL_RE = re.compile(r"\bfor\s+(.+)$", re.IGNORECASE)
_FIELD_TOKEN_RE = re.compile(r"(?:get\(|\[)(?:['\"])([A-Za-z0-9_]+)(?:['\"])")
_NEGATED_IDENTIFIER_RE = re.compile(r"\bif\s+not\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE)
_CAN_ACTION_RE = re.compile(r"\bcan_([a-z][a-z0-9_]*)\b", re.IGNORECASE)
_PERMISSION_LITERAL_RE = re.compile(r"\b(?:has_permission|permission|scope)\s*\(\s*['\"]([a-z][a-z0-9_-]*)['\"]", re.IGNORECASE)
_STATUS_LITERAL_RE = re.compile(r"\b(?:status|state)\s*==\s*['\"]([a-z][a-z0-9_-]*)['\"]", re.IGNORECASE)
_STRING_LITERAL_RE = re.compile(r"['\"]([A-Za-z][A-Za-z0-9_-]*)['\"]")
_PATH_TOKEN_SPLIT_RE = re.compile(r"[_\-/]+")

_GENERIC_PATH_TOKENS = frozenset(
    {
        "src",
        "app",
        "core",
        "service",
        "services",
        "policy",
        "policies",
        "validator",
        "validation",
        "workflow",
        "state",
        "transition",
        "model",
        "models",
        "schema",
        "schemas",
        "config",
        "settings",
        "helpers",
        "helper",
        "utils",
        "common",
        "module",
    }
)

DISCOVERY_ACCEPTED = "accepted_for_validation"
DISCOVERY_DROPPED_TECHNICAL = "dropped_technical_artifact"
DISCOVERY_DROPPED_MISSING_ANCHOR = "dropped_missing_enforcement_anchor"
DISCOVERY_DROPPED_MISSING_SEMANTICS = "dropped_missing_business_semantics"


@dataclass(frozen=True)
class CodeSurface:
    path: str
    language: str
    surface_type: str


@dataclass(frozen=True)
class CodeRuleCandidate:
    text: str
    path: str
    language: str
    line_start: int
    line_end: int
    extractor_kind: str
    confidence: str
    semantic_type: str
    evidence_snippet: str
    enforcement_anchor_type: str
    evidence_kind: str = ""


@dataclass(frozen=True)
class CodeDiscoveryOutcome:
    path: str
    language: str
    line_start: int
    status: str
    source_text: str
    evidence_snippet: str
    enforcement_anchor_type: str = ""
    semantic_type: str = ""
    evidence_kind: str = ""


@dataclass(frozen=True)
class CodeRuleExtractionResult:
    candidates: tuple[CodeRuleCandidate, ...]
    outcomes: tuple[CodeDiscoveryOutcome, ...]

    @property
    def raw_candidate_count(self) -> int:
        return len(self.outcomes)

    @property
    def dropped_candidate_count(self) -> int:
        return sum(1 for item in self.outcomes if item.status != DISCOVERY_ACCEPTED)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)
    
    @property
    def dropped_non_business_surface_count(self) -> int:
        return sum(1 for item in self.outcomes if item.status == DISCOVERY_DROPPED_NON_BUSINESS_SURFACE)
    
    @property
    def dropped_schema_only_count(self) -> int:
        return sum(1 for item in self.outcomes if item.status == DISCOVERY_DROPPED_SCHEMA_ONLY)
    
    @property
    def dropped_non_executable_normative_text_count(self) -> int:
        return sum(1 for item in self.outcomes if item.status == DISCOVERY_DROPPED_NON_EXECUTABLE_NORMATIVE_TEXT)
    
    @property
    def accepted_business_enforcement_count(self) -> int:
        return sum(1 for item in self.outcomes if item.status == DISCOVERY_ACCEPTED and item.evidence_kind == "executable_code")


def _language_for_suffix(suffix: str) -> str:
    mapping = {
        ".py": "python",
        ".go": "go",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".java": "java",
        ".kt": "kotlin",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
    }
    return mapping.get(suffix.lower(), "unknown")


def _surface_type_for_path(path: str) -> str:
    lower = path.lower()
    # Check for non-business surfaces first
    if any(token in lower for token in ("test", "spec", "__test__", ".github", "ci", "scripts", "docs")):
        return SURFACE_KIND_META_GOVERNANCE
    if any(token in lower for token in ("schema", "config", "settings")):
        return SURFACE_KIND_SCHEMA_CONFIG
    if any(token in lower for token in ("docstring", "comment", "docs")):
        return SURFACE_KIND_DOCSTRING_OR_COMMENT
    if any(token in lower for token in ("lint", "style", "format", "prettier", "eslint")):
        return SURFACE_KIND_LINT_OR_STYLE
    if any(token in lower for token in ("infra", "framework", "lib", "utils", "helper")):
        return SURFACE_KIND_INFRA_FRAMEWORK
    # Business domain surfaces
    if any(token in lower for token in ("validator", "validation")):
        return SURFACE_KIND_BUSINESS_DOMAIN_CODE
    if any(token in lower for token in ("permission", "auth", "policy", "acl")):
        return SURFACE_KIND_BUSINESS_DOMAIN_CODE
    if any(token in lower for token in ("workflow", "state_machine", "transition", "fsm")):
        return SURFACE_KIND_BUSINESS_DOMAIN_CODE
    if any(token in lower for token in ("model", "schema", "entity")):
        return SURFACE_KIND_BUSINESS_DOMAIN_CODE
    # Default to conservative - unknown paths are not automatically business domain
    return SURFACE_KIND_META_GOVERNANCE


def _classify_surface_kind(surface: CodeSurface, line_content: str) -> str:
    """Classify surface kind based on path and content."""
    path_lower = surface.path.lower()
    line_lower = line_content.lower()
    
    # Meta-governance detection (based on path)
    if any(token in path_lower for token in ("test", "spec", "__test__", ".github", "ci", "scripts", "docs")):
        return SURFACE_KIND_META_GOVERNANCE
    
    # Schema/config detection (based on path)
    if any(token in path_lower for token in ("schema", "config", "settings")):
        return SURFACE_KIND_SCHEMA_CONFIG
    
    # Docstring/comment detection (based on path)
    if any(token in path_lower for token in ("docstring", "comment")):
        return SURFACE_KIND_DOCSTRING_OR_COMMENT
    
    # Lint/style detection (based on path)
    if any(token in path_lower for token in ("lint", "style", "format", "prettier", "eslint")):
        return SURFACE_KIND_LINT_OR_STYLE
    
    # Infrastructure/framework detection (based on path)
    if any(token in path_lower for token in ("infra", "framework", "lib", "utils", "helper")):
        return SURFACE_KIND_INFRA_FRAMEWORK
    
    # Content-based overrides for specific cases
    # Docstring/Comment overrides (regardless of path) - be more inclusive
    line_stripped = line_lower.lstrip()
    if (line_stripped.startswith(("#", "//")) or 
        ("/*" in line_lower and "*/" in line_lower) or
        line_stripped.startswith('"""') or line_stripped.startswith("'''") or
        line_stripped.endswith('"""') or line_stripped.endswith("'''")):
        return SURFACE_KIND_DOCSTRING_OR_COMMENT
    
    # More precise schema/config detection - only for clear schema definition patterns
    # Avoid false positives on business rules that happen to contain schema-like words
    stripped_line = line_lower.strip()
    if (stripped_line.startswith(("required:", "optional:", "properties:", "type:", "minimum:", "maximum:", "enum:", "format:", "pattern:")) 
        and ":" in stripped_line and len(stripped_line.split(":")[0]) < 20):
        # Likely a YAML schema key definition
        return SURFACE_KIND_SCHEMA_CONFIG
    
    # For actual code files (Python, Go, TypeScript, Java, etc.), default to business domain
    # These are the primary sources for executable enforcement evidence
    code_languages = {"python", "go", "typescript", "javascript", "java", "kotlin", "sql"}
    if surface.language.lower() in code_languages:
        return SURFACE_KIND_BUSINESS_DOMAIN_CODE
    
    # For non-code files (YAML, JSON, etc.), be conservative and require explicit classification
    # These are more likely to be schema/config/meta-governance
    return SURFACE_KIND_META_GOVERNANCE


def _has_real_business_domain_context(line: str, anchor: str, semantic_type: str) -> bool:
    """Check if line contains real business domain context."""
    line_lower = line.lower()
    
    # Reject clearly generic technical subjects without business context
    generic_subjects = {"value", "item", "data", "object"}
    if any(subject in line_lower.split() for subject in generic_subjects):
        business_indicators = {"customer", "order", "payment", "invoice", "account", "user", 
                              "product", "transaction", "subscription", "billing", "shipping"}
        if not any(indicator in line_lower for indicator in business_indicators):
            return False
    
    # field is a generic technical term - reject unless there's clear business context
    if "field" in line_lower.split():
        business_indicators = {"customer", "order", "payment", "invoice", "account", "user", 
                              "product", "transaction", "subscription", "billing", "shipping"}
        if not any(indicator in line_lower for indicator in business_indicators):
            return False
    
    # payload is a generic technical term - reject unless there's clear business context
    if "payload" in line_lower.split():
        business_indicators = {"customer", "order", "payment", "invoice", "account", "user", 
                              "product", "transaction", "subscription", "billing", "shipping"}
        if not any(indicator in line_lower for indicator in business_indicators):
            return False
    
    # Validator needs business context for non-permission/non-required-field types
    if anchor == "validator":
        business_semantic_types = {"permission", "required-field", "transition", 
                                  "uniqueness", "audit", "retention", "invariant"}
        if semantic_type not in business_semantic_types:
            business_entities = {"customer", "order", "payment", "invoice", "account", "user"}
            if not any(entity in line_lower for entity in business_entities):
                return False
    
    return True


def _is_executable_enforcement_evidence(surface_kind: str, line: str) -> bool:
    """Check if evidence represents executable enforcement."""
    non_executable = {
        SURFACE_KIND_META_GOVERNANCE,
        SURFACE_KIND_SCHEMA_CONFIG,
        SURFACE_KIND_DOCSTRING_OR_COMMENT,
        SURFACE_KIND_LINT_OR_STYLE,
        SURFACE_KIND_INFRA_FRAMEWORK
    }
    
    if surface_kind in non_executable:
        return False
    
    line_lower = line.lower()
    
    # Additional checks for schema/config
    if surface_kind == SURFACE_KIND_SCHEMA_CONFIG:
        enforcement_indicators = {"must", "shall", "required", "forbidden", "validate", "enforce"}
        if not any(indicator in line_lower for indicator in enforcement_indicators):
            return False
        business_indicators = {"customer", "order", "payment", "invoice", "account"}
        if not any(indicator in line_lower for indicator in business_indicators):
            return False
    
    # Docstrings/comments never executable evidence
    if surface_kind == SURFACE_KIND_DOCSTRING_OR_COMMENT:
        return False
    
    return True


def discover_code_surfaces(repo_root: Path) -> list[CodeSurface]:
    surfaces: list[CodeSurface] = []
    for current_root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        root = Path(current_root)
        for filename in files:
            suffix = Path(filename).suffix.lower()
            if suffix not in _CODE_SUFFIXES:
                continue
            absolute = root / filename
            try:
                rel = str(absolute.relative_to(repo_root)).replace("\\", "/")
            except ValueError:
                continue
            surfaces.append(
                CodeSurface(
                    path=rel,
                    language=_language_for_suffix(suffix),
                    surface_type=_surface_type_for_path(rel),
                )
            )
    return surfaces


def _candidate_text(index: int, canonical_sentence: str) -> str:
    return f"BR-C{index:03d}: {canonical_sentence}"


def _line_is_non_normative(line: str) -> bool:
    return bool(_NON_NORMATIVE_LINE_RE.search(line.strip()))


def _line_is_technical_artifact(line: str) -> bool:
    probe = line.strip()
    if not probe:
        return True
    if _TECHNICAL_ARTIFACT_RE.search(probe):
        return True
    if _PATH_FRAGMENT_RE.search(probe):
        return True
    if _IDENTIFIER_CHAIN_RE.search(probe) and not _SEMANTIC_KEYWORD_RE.search(probe):
        return True
    if _WEAK_TECHNICAL_ONLY_RE.search(probe) and not _NORMATIVE_COMMENT_RE.search(probe) and not _SEMANTIC_KEYWORD_RE.search(probe):
        return True
    return False


def _detect_anchor(line: str) -> str:
    if _DECLARATION_LINE_RE.match(line.strip()):
        return ""
    for anchor, pattern in _ANCHOR_PATTERNS:
        if pattern.search(line):
            return anchor
    if re.search(r"\b(log_event|audit|journal|append_log)\b", line, re.IGNORECASE):
        return "validator"
    return ""


def _looks_like_normative_comment(line: str) -> bool:
    if not _COMMENT_PREFIX_RE.match(line):
        return False
    return bool(_NORMATIVE_COMMENT_RE.search(line))


def _anchor_from_context(lines: list[str], index: int) -> tuple[str, str]:
    current = lines[index].strip()
    if not _looks_like_normative_comment(current):
        anchor = _detect_anchor(current)
        if anchor:
            return anchor, current
        return "", ""

    for offset in (1, 2, -1, -2):
        probe_idx = index + offset
        if probe_idx < 0 or probe_idx >= len(lines):
            continue
        nearby = lines[probe_idx].strip()
        nearby_anchor = _detect_anchor(nearby)
        if nearby_anchor:
            return nearby_anchor, nearby
    return "", ""


def _semantic_match(text: str) -> tuple[str, str]:
    for semantic_type, sentence, pattern in _SEMANTIC_PATTERNS:
        if pattern.search(text):
            return semantic_type, sentence
    return "", ""


def _semantic_probe(lines: list[str], index: int, evidence_line: str) -> str:
    probes = [lines[index].strip(), evidence_line]
    for offset in (-2, -1, 1, 2):
        probe_idx = index + offset
        if probe_idx < 0 or probe_idx >= len(lines):
            continue
        probe = lines[probe_idx].strip()
        if probe:
            probes.append(probe)
    return " ".join(part for part in probes if part)


def _humanize_token(token: str) -> str:
    cleaned = token.strip().strip("`'\"")
    if not cleaned:
        return ""
    words = [part for part in _PATH_TOKEN_SPLIT_RE.split(cleaned) if part]
    if not words:
        return ""
    normalized: list[str] = []
    for word in words:
        lowered = word.lower()
        if lowered == "id":
            normalized.append("ID")
        elif len(word) <= 2:
            normalized.append(word.upper())
        else:
            normalized.append(lowered)
    phrase = " ".join(normalized).strip()
    if not phrase:
        return ""
    return phrase[0].upper() + phrase[1:]


def _clean_context_tail(value: str, *, allow_identifier: bool = False) -> str:
    probe = str(value or "").strip().strip("`'\".,:;()[]{}")
    if not probe:
        return ""
    if _PATH_FRAGMENT_RE.search(probe):
        return ""
    if _DISCOVERY_TECHNICAL_ARTIFACT_RE.search(probe):
        return ""
    if not allow_identifier and _line_is_discovery_technical_artifact(probe):
        return ""
    return _humanize_token(probe)


def _path_context(path: str) -> str:
    path_without_suffix = str(Path(path).with_suffix(""))
    for token in reversed(_PATH_TOKEN_SPLIT_RE.split(path_without_suffix)):
        lowered = token.lower()
        if not lowered or lowered in _GENERIC_PATH_TOKENS:
            continue
        return _humanize_token(token)
    return ""


def _extract_context_tail(semantic_type: str, probe: str, path: str) -> str:
    text = str(probe or "")
    comment_tail = _COMMENT_FOR_TAIL_RE.search(text)
    if comment_tail:
        cleaned_tail = _clean_context_tail(comment_tail.group(1))
        if cleaned_tail:
            return cleaned_tail

    if semantic_type == "required-field":
        field_match = _FIELD_TOKEN_RE.search(text)
        if field_match:
            cleaned_tail = _clean_context_tail(field_match.group(1), allow_identifier=True)
            if cleaned_tail:
                return cleaned_tail
        negated_identifier = _NEGATED_IDENTIFIER_RE.search(text)
        if negated_identifier:
            cleaned_tail = _clean_context_tail(negated_identifier.group(1), allow_identifier=True)
            if cleaned_tail:
                return cleaned_tail

    if semantic_type == "permission":
        action_match = _CAN_ACTION_RE.search(text) or _PERMISSION_LITERAL_RE.search(text)
        if action_match:
            cleaned_tail = _clean_context_tail(action_match.group(1), allow_identifier=True)
            if cleaned_tail:
                return f"{cleaned_tail} operations"

    if semantic_type == "transition":
        status_match = _STATUS_LITERAL_RE.search(text)
        if status_match:
            cleaned_tail = _clean_context_tail(status_match.group(1), allow_identifier=True)
            if cleaned_tail:
                return f"{cleaned_tail} status"

    if semantic_type in {"audit", "retention", "uniqueness", "invariant"}:
        for literal in _STRING_LITERAL_RE.findall(text):
            lowered = literal.lower()
            if lowered in {"unauthorized", "forbidden", "required", "invalid", "audit", "error"}:
                continue
            cleaned_tail = _clean_context_tail(literal, allow_identifier=True)
            if cleaned_tail:
                return cleaned_tail

    return _path_context(path)


def _render_contextual_sentence(semantic_type: str, probe: str, path: str) -> str:
    tail = _extract_context_tail(semantic_type, probe, path)
    if semantic_type == "permission":
        return f"{tail} must deny unauthorized access." if tail else "Access control must deny unauthorized operations."
    if semantic_type == "required-field":
        return f"{tail} must be present before processing." if tail else "Required fields must be validated before processing."
    if semantic_type == "transition":
        return f"{tail} transitions must be blocked when invalid." if tail else "Disallowed lifecycle transitions must be blocked."
    if semantic_type == "uniqueness":
        return f"{tail} records must reject duplicates." if tail else "Uniqueness constraints must reject duplicates."
    if semantic_type == "audit":
        return f"{tail} must record audit events." if tail else "Audit events must be recorded for protected actions."
    if semantic_type == "retention":
        return f"{tail} must enforce retention or purge constraints." if tail else "Retention policies must enforce archival or purge constraints."
    if semantic_type == "invariant":
        return f"{tail} must remain valid before state changes." if tail else "Domain invariants must be enforced before state mutation."
    _, default_sentence = _semantic_match(probe)
    return default_sentence


def _line_is_discovery_technical_artifact(line: str) -> bool:
    probe = line.strip()
    if not probe:
        return False
    if _DECLARATION_LINE_RE.match(probe):
        return False
    if _DISCOVERY_TECHNICAL_ARTIFACT_RE.search(probe):
        return True
    if _PATH_FRAGMENT_RE.search(probe):
        return True
    if _NAKED_IDENTIFIER_RE.fullmatch(probe):
        return True
    if _IDENTIFIER_CHAIN_RE.search(probe) and not _SEMANTIC_KEYWORD_RE.search(probe):
        return True
    if _WEAK_TECHNICAL_ONLY_RE.search(probe) and not _NORMATIVE_COMMENT_RE.search(probe) and not _SEMANTIC_KEYWORD_RE.search(probe):
        return True
    return False


def _classify_discovery_line(lines: list[str], index: int) -> tuple[str, str, str, str]:
    current = lines[index].strip()
    if not current:
        return "", "", "", ""

    anchor, evidence_line = _anchor_from_context(lines, index)
    semantic_type, sentence = _semantic_match(f"{current} {evidence_line}".strip())
    if anchor and not semantic_type:
        semantic_type, sentence = _semantic_match(_semantic_probe(lines, index, evidence_line))
    current_semantic_type, _ = _semantic_match(current)

    if not anchor and _line_is_discovery_technical_artifact(current):
        return DISCOVERY_DROPPED_TECHNICAL, anchor, semantic_type, evidence_line or current
    if anchor:
        if semantic_type:
            return DISCOVERY_ACCEPTED, anchor, semantic_type, evidence_line or current
        return DISCOVERY_DROPPED_MISSING_SEMANTICS, anchor, "", evidence_line or current
    if _looks_like_normative_comment(current):
        return DISCOVERY_DROPPED_MISSING_ANCHOR, "", current_semantic_type, current
    return "", "", "", ""


def extract_code_rule_candidates_with_diagnostics(repo_root: Path) -> tuple[CodeRuleExtractionResult, bool]:
    surfaces = discover_code_surfaces(repo_root)
    candidates: list[CodeRuleCandidate] = []
    outcomes: list[CodeDiscoveryOutcome] = []
    idx = 1
    for surface in surfaces:
        path = repo_root / surface.path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        split_lines = text.splitlines()
        for line_no, raw_line in enumerate(split_lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            
            # Classify surface kind
            surface_kind = _classify_surface_kind(surface, line)
            
            status, anchor, semantic_type, evidence_line = _classify_discovery_line(split_lines, line_no - 1)
            if not status:
                continue

            evidence_snippet = evidence_line or line
            
            # Apply enhanced acceptance criteria
            is_business_domain = surface_kind == SURFACE_KIND_BUSINESS_DOMAIN_CODE
            has_real_enforcement = bool(anchor)
            has_business_context = _has_real_business_domain_context(line, anchor, semantic_type)
            is_executable_evidence = _is_executable_enforcement_evidence(surface_kind, line)
            
            # Check for schema-only content
            is_schema_only = surface_kind == SURFACE_KIND_SCHEMA_CONFIG
            
            # Determine final status based on all criteria
            final_status = status  # Keep original if not overridden by our checks
            if is_schema_only and not has_business_context:
                final_status = DISCOVERY_DROPPED_SCHEMA_ONLY
            elif not is_business_domain:
                final_status = DISCOVERY_DROPPED_NON_BUSINESS_SURFACE
            elif not has_real_enforcement:
                final_status = DISCOVERY_DROPPED_MISSING_ANCHOR
            elif not has_business_context:
                final_status = DISCOVERY_DROPPED_MISSING_SEMANTICS
            elif not is_executable_evidence:
                final_status = DISCOVERY_DROPPED_NON_EXECUTABLE_NORMATIVE_TEXT
            
            # Determine evidence_kind with finer categories
            if is_business_domain and has_real_enforcement and has_business_context and is_executable_evidence:
                evidence_kind_val = "executable_code"
            elif surface_kind == SURFACE_KIND_SCHEMA_CONFIG:
                evidence_kind_val = "schema"
            elif surface_kind == SURFACE_KIND_DOCSTRING_OR_COMMENT:
                evidence_kind_val = "docstring"
            elif surface_kind == SURFACE_KIND_LINT_OR_STYLE:
                evidence_kind_val = "lint"
            elif surface_kind == SURFACE_KIND_INFRA_FRAMEWORK:
                evidence_kind_val = "infra"
            elif surface_kind == SURFACE_KIND_META_GOVERNANCE:
                evidence_kind_val = "meta"
            else:
                evidence_kind_val = "other"
            
            outcome = CodeDiscoveryOutcome(
                path=surface.path,
                language=surface.language,
                line_start=line_no,
                status=final_status,
                source_text=line,
                evidence_snippet=evidence_snippet[:220],
                enforcement_anchor_type=anchor,
                semantic_type=semantic_type,
                evidence_kind=evidence_kind_val
            )
            outcomes.append(outcome)

            if final_status != DISCOVERY_ACCEPTED:
                continue

            semantic_probe = _semantic_probe(split_lines, line_no - 1, evidence_line)
            sentence = _render_contextual_sentence(semantic_type, semantic_probe, surface.path)
            candidates.append(
                CodeRuleCandidate(
                    text=_candidate_text(idx, sentence),
                    path=surface.path,
                    language=surface.language,
                    line_start=line_no,
                    line_end=line_no,
                    extractor_kind="pattern-deterministic",
                    confidence="medium",
                    semantic_type=semantic_type,
                    evidence_snippet=evidence_snippet[:220],
                    enforcement_anchor_type=anchor,
                    evidence_kind=evidence_kind_val,
                )
            )
            idx += 1

    return CodeRuleExtractionResult(candidates=tuple(candidates), outcomes=tuple(outcomes)), True


def extract_code_rule_candidates(repo_root: Path) -> tuple[list[CodeRuleCandidate], bool]:
    result, ok = extract_code_rule_candidates_with_diagnostics(repo_root)
    return list(result.candidates), ok
