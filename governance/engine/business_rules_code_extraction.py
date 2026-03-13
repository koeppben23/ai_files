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

_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("permission", "permission checks", re.compile(r"(permission|authorize|authz|acl|requires?_role)", re.IGNORECASE)),
    ("invariant", "invariants", re.compile(r"(\bassert\b|invariant|must_not|forbid|immutable)", re.IGNORECASE)),
    ("transition", "state transitions", re.compile(r"(\bstatus\b.*(==|!=|\bin\b)|transition|state_machine)", re.IGNORECASE)),
    ("required-field", "required field checks", re.compile(r"(if\s+not\s+\w+|required\s*=\s*true|required:)" , re.IGNORECASE)),
    ("uniqueness", "uniqueness checks", re.compile(r"(unique|duplicate|already\s+exists|conflict)", re.IGNORECASE)),
    ("audit", "audit requirements", re.compile(r"(audit|log_event|append_log|journal)", re.IGNORECASE)),
    ("retention", "retention constraints", re.compile(r"(retention|archive|soft_delete|purge)", re.IGNORECASE)),
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


def _candidate_text(index: int, semantic_label: str, line: str) -> str:
    hint_words = re.findall(r"[A-Za-z_]{3,}", line)
    hint = " ".join(hint_words[:6]).lower()
    tail = hint if hint else semantic_label
    return f"BR-C{index:03d}: {semantic_label.capitalize()} must be enforced for {tail}"


def extract_code_rule_candidates(repo_root: Path) -> tuple[list[CodeRuleCandidate], bool]:
    surfaces = discover_code_surfaces(repo_root)
    candidates: list[CodeRuleCandidate] = []
    idx = 1
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
            for semantic_type, label, pattern in _PATTERNS:
                if not pattern.search(line):
                    continue
                candidates.append(
                    CodeRuleCandidate(
                        text=_candidate_text(idx, label, line),
                        path=surface.path,
                        language=surface.language,
                        line_start=line_no,
                        line_end=line_no,
                        extractor_kind="pattern-deterministic",
                        confidence="medium",
                        semantic_type=semantic_type,
                    )
                )
                idx += 1
                break
    return candidates, True
