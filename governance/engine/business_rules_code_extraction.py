from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


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
)

_SEMANTIC_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("permission", "Access control must deny unauthorized operations.", re.compile(r"(permission|authorize|authz|acl|requires?_role|forbidden|unauthorized)", re.IGNORECASE)),
    ("required-field", "Required fields must be validated before processing.", re.compile(r"(required|missing|if\s+not\s+\w+|not\s+\w+|validate|required\s*=\s*true)" , re.IGNORECASE)),
    ("transition", "Disallowed lifecycle transitions must be blocked.", re.compile(r"(status|state|transition|state_machine|lifecycle)", re.IGNORECASE)),
    ("uniqueness", "Uniqueness constraints must reject duplicates.", re.compile(r"(unique|duplicate|already\s+exists|conflict)", re.IGNORECASE)),
    ("audit", "Audit events must be recorded for protected actions.", re.compile(r"(audit|log_event|append_log|journal|audit_log)", re.IGNORECASE)),
    ("retention", "Retention policies must enforce archival or purge constraints.", re.compile(r"(retention|archive|soft_delete|purge|ttl)", re.IGNORECASE)),
    ("invariant", "Domain invariants must be enforced before state mutation.", re.compile(r"(assert|invariant|must_not|forbid|immutable|constraint)", re.IGNORECASE)),
)

_NON_NORMATIVE_LINE_RE = re.compile(
    r"^(from\s+\S+\s+import\s+\S+|import\s+\S+|@\w+|class\s+\w+\(|def\s+\w+\(|dataclass\b)",
    re.IGNORECASE,
)


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
    if any(token in lower for token in ("validator", "validation")):
        return "validator"
    if any(token in lower for token in ("permission", "auth", "policy", "acl")):
        return "permissions"
    if any(token in lower for token in ("workflow", "state_machine", "transition", "fsm")):
        return "workflow"
    if any(token in lower for token in ("model", "schema", "entity")):
        return "model"
    if any(token in lower for token in ("config", "settings")):
        return "config"
    return "service"


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
            except Exception:
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


def _detect_anchor(line: str) -> str:
    for anchor, pattern in _ANCHOR_PATTERNS:
        if pattern.search(line):
            return anchor
    if re.search(r"\b(log_event|audit|journal|append_log)\b", line, re.IGNORECASE):
        return "validator"
    return ""


def extract_code_rule_candidates(repo_root: Path) -> tuple[list[CodeRuleCandidate], bool]:
    surfaces = discover_code_surfaces(repo_root)
    candidates: list[CodeRuleCandidate] = []
    idx = 1
    seen_clusters: set[tuple[str, str, str]] = set()
    for surface in surfaces:
        path = repo_root / surface.path
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if _line_is_non_normative(line):
                continue
            anchor = _detect_anchor(line)
            if not anchor:
                continue
            for semantic_type, sentence, pattern in _SEMANTIC_PATTERNS:
                if not pattern.search(line):
                    continue
                path_family = "/".join(surface.path.split("/")[:2]) if "/" in surface.path else surface.path
                cluster_key = (semantic_type, sentence.lower(), path_family)
                if cluster_key in seen_clusters:
                    continue
                seen_clusters.add(cluster_key)
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
                        evidence_snippet=line[:220],
                        enforcement_anchor_type=anchor,
                    )
                )
                idx += 1
                break
    return candidates, True
