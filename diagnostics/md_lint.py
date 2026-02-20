#!/usr/bin/env python3
"""MD-SSOT Linter - Enforces "MD nur Schienen" rule.

Validates that markdown files contain only output/format guidance,
not execution/policy/orchestration logic.

Rules:
- MD001: Execution Loop/Retry/Cycles (FORBIDDEN)
- MD002: Phase/Router/Next-State Steuerung (FORBIDDEN)
- MD003: Host/Tool Execution Commands (FORBIDDEN)
- MD004: Policy/Authority Sprache (only output-context allowed)
- MD005: Interaktivität/Approvals/Prompt Budget (FORBIDDEN)
- MD006: Evidence Schema/Validation (declarative only)
- MD007: Authority Blocks/Algorithm Sections (FORBIDDEN)
- MD008: Non-normative Mirror Guard (for AGENTS.md)

Exit codes:
  0: No violations
  1: Violations found
  2: Parse error
  3: Configuration error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Finding:
    """A single lint finding."""
    rule_id: str
    severity: str
    file_path: str
    line: int
    column: int
    match: str
    snippet_hash: str
    context_hash: str
    message: str
    
    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "file": self.file_path,
            "line": self.line,
            "col": self.column,
            "match": self.match,
            "snippet_hash": self.snippet_hash,
            "context_hash": self.context_hash,
            "message": self.message,
        }


@dataclass
class Rule:
    """A lint rule definition."""
    rule_id: str
    name: str
    description: str
    patterns: tuple[str, ...]
    exceptions: tuple[str, ...] = ()
    severity: str = "error"
    message: str = ""


# Normalization for stable hashes
def normalize(text: str) -> str:
    """Normalize text for hashing."""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[.,;:!?]+$", "", text)
    return text


def hash_text(text: str) -> str:
    """Generate SHA256 hash of normalized text."""
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:16]


def hash_context(prev: str, line: str, next_line: str) -> str:
    """Generate context hash."""
    ctx = f"{prev}|||{line}|||{next_line}"
    return hash_text(ctx)


# Rule definitions
RULES: tuple[Rule, ...] = (
    # MD001 - Execution Loop/Retry/Cycles
    Rule(
        rule_id="MD001",
        name="execution-loop-cycles",
        description="Execution loop/retry/cycles are kernel-owned, not MD",
        patterns=(
            r"\bloop\s+back\b",
            r"\bmax(imum)?\s+\d+\s+(full\s+)?cycles?\b",
            r"\bsecond\s+pass\b",
            r"\bexecute\s+.*\bretry\b",
            r"\bthen\s+retry\b",
            r"\bretry\s+execution\b",
            r"\bmax\s+retries\b",
            r"\btry\s+again\b",
            r"\buntil\s+success\b",
            r"\bkeep\s+going\b",
            r"\biterative\s+refinement\b.*\b(must|shall|required)\b",
            r"\bmust\s+loop\b",
            r"\bmust\s+be\s+resolved\s+before\s+proceeding\b",
        ),
        exceptions=(
            r"\bretry\s+guidance\b",
            r"\brestart_hint\b",
            r"\bmay\s+trigger\s+second\s+pass\b",
            r"\bkernel-managed\b.*\bsecond\s+pass\b",
        ),
        severity="error",
        message="Execution loop/retry logic is kernel-owned. Use kernel config, not MD.",
    ),
    
    # MD002 - Phase/Router/Next-State
    Rule(
        rule_id="MD002",
        name="phase-router-state",
        description="Phase/router/next-state steering is kernel-owned",
        patterns=(
            r"\bphase\s*\d+(\.\d+)?\b.*\b(must|shall|always)\b",
            r"\btransition(_id)?\b.*\bmust\b",
            r"\benter\s+phase\b",
            r"\bgo\s+to\s+phase\b",
            r"\bmust\s+route\b",
            r"\bstate\s+machine\b.*\bmust\b",
            r"\bphase\s*\d+\b.*\bmay\s+be\s+executed\s+only\b",
        ),
        exceptions=(
            r"\boutput\s+.*\b(must|shall|required)\b",
            r"\bresponse\s+.*\b(must|shall|required)\b",
            r"^\*\s*Phase\s*\d+",
            r"\b(kernel|informational)[- ]enforced\b",
            r"\(kernel-enforced",
            r"\(informational",
            r"only\s+when\b",
            r"active\s+when\b",
            r"\bworkflow\s+(MUST\s+)?output\b",
            r"\bMUST\s+output\b",
            r"\bMUST\s+include\b",
            r"\bMUST\s+write\b",
            r"\bMUST\s+present\b",
            r"\bMUST\s+reference\b",
            r"\bMUST\s+contain\b",
            r"\bMUST\s+record\b",
        ),
        severity="error",
        message="Phase/router/next-state steering is kernel-owned. Use kernel config.",
    ),

    # MD009 - Operational policy markers in MD
    Rule(
        rule_id="MD009",
        name="operational-policy-markers",
        description="Operational policy markers are kernel-owned",
        patterns=(
            r"\bMode\s*=\s*BLOCKED\b",
            r"\bNext\s*=\s*['\"]?BLOCKED-[A-Z-]+",
            r"\bsearch\s+order\s*:",
            r"\brequired\s+input\s*:",
            r"\bresume\s+pointer\s*:",
            r"\brecovery\s+steps\s*:",
        ),
        exceptions=(
            r"\[BLOCKED\]",
            r"machine-readable",
            r"output format",
            r"informational",
        ),
        severity="error",
        message="Operational policy markers belong in kernel/config, not MD.",
    ),
    
    # MD003 - Host/Tool Execution
    Rule(
        rule_id="MD003",
        name="host-execution",
        description="Host/tool execution commands are kernel-owned",
        patterns=(
            r"\bhost\s+executes?\b",
            r"\bruns?\s+scripts?\b",
            r"\binvokes?\b.*\bscripts?\b",
            r"\brun\s+(this|the)\s+script\b",
            r"\bexecute\s+(command|script|tool)\b",
            r"\bcall\s+/[\w/]+\b",
            r"\bopen\s+terminal\b",
            r"\bpowershell\b.*\bmust\b",
            r"\bcmd\.exe\b.*\bmust\b",
            r"\bbash\b.*\bmust\b",
        ),
        exceptions=(
            r"\*\*Implementation Reference:\*\*",
            r"The\s+\w+\s+host\s+executes",
            r"Implementation Reference:",
        ),
        severity="error",
        message="Host/tool execution is kernel-owned. Remove from MD.",
    ),
    
    # MD004 - Policy/Authority Language
    # This rule flags policy language outside of output/format context.
    # In a pure "output contract" MD file, must/shall/required should only appear
    # in the context of describing what the OUTPUT should contain.
    Rule(
        rule_id="MD004",
        name="policy-authority",
        description="Policy/authority language only allowed in output context",
        patterns=(
            r"\bworkflow\s+must\b",
            r"\bmust\s+execute\b",
            r"\bmust\s+perform\b",
            r"\bmust\s+run\b",
            r"\bmust\s+load\b",
            r"\bmust\s+reload\b",
            r"\bmust\s+validate\b",
            r"\bmust\s+check\b",
            r"\bmust\s+verify\b",
            r"\bmust\s+ensure\b",
            r"\bmust\s+enforce\b",
            r"\bmust\s+apply\b",
            r"\bmust\s+transition\b",
            r"\bmust\s+route\b",
            r"\bmust\s+enter\b",
            r"\bmust\s+not\s+(require|generate|execute|run|load|create)\b",
            r"\bshall\s+(execute|perform|run|load|validate|check|verify|ensure)\b",
            r"\bis\s+(strictly\s+)?required\s+to\b",
            r"\brequired\s+before\s+(execution|proceeding)\b",
        ),
        exceptions=(
            r"\boutput\s+.*\b(must|shall|required)\b",
            r"\bresponse\s+.*\b(must|shall|required)\b",
            r"\bformat\s+.*\b(must|shall|required)\b",
            r"\brender\s+.*\b(must|shall|required)\b",
            r"\btemplate\s+.*\b(must|shall|required)\b",
            r"\bsection\s+.*\b(must|shall|required)\b",
            r"\binclude\s+.*\b(must|shall|required)\b",
            r"\bmust\s+appear\s+in\b",
            r"\bmust\s+be\s+present\b",
            r"\bmust\s+contain\b",
            r"\bmust\s+include\b",
            r"\bmust\s+have\b",
            r"\bmust\s+match\b",
            r"\bmust\s+follow\b",
            r"\bfield\s+.*\bmust\b",
            r"\bvalue\s+.*\bmust\b",
            r"\bkey\s+.*\bmust\b",
            r"\bproperty\s+.*\bmust\b",
            r"\battribute\s+.*\bmust\b",
            r"\bschema\s+.*\bmust\b",
            r"\bJSON\s+.*\bmust\b",
            r"\bYAML\s+.*\bmust\b",
            r"\brequired\s+(field|key|property|value|attribute)\b",
            r"\bRequired(ED)?:\s*$",
        ),
        severity="warning",
        message="Policy/authority language without output context is kernel-owned.",
    ),
    
    # MD005 - Interactivity/Budget
    Rule(
        rule_id="MD005",
        name="interactivity-budget",
        description="Interactivity/approvals/prompt budget are kernel-owned",
        patterns=(
            r"\bprompt\s+budget\b",
            r"\bmax_total\b",
            r"\bmax_repo_docs\b",
            r"\bask[- ]before\b.*\b(kernel|mode|policy)\b",
            r"\bhuman\s+(help|assist|review)\b.*\b(must|shall|required)\b",
            r"\bmust\s+(get|obtain|require)\s+(approval|confirmation)\b",
            r"\bapproval\s+(is\s+)?required\s+before\b",
            r"\bexact\s+confirmation\b",
            r"\bYES\b.*\brequired\b",
            r"\b0\s+prompts\b.*\benforced\b",
        ),
        severity="error",
        message="Interactivity/budget rules are kernel-owned. Use kernel config.",
    ),
    
    # MD006 - Evidence Schema/Validation
    Rule(
        rule_id="MD006",
        name="evidence-schema",
        description="Evidence schema/validation is declarative only in MD",
        patterns=(
            r"\bschema\b.*\bmust\s+validate\b",
            r"\breason\s+code\s+schema\b.*\bmust\b",
            r"\bemit\b.*\bwith\s+reason\b.*\bmust\s+validate\b",
            r"\byaml\s+schema\b.*\bmust\s+be\s+defined\b",
            r"\bjson\s+schema\b.*\bmust\s+be\s+defined\b",
        ),
        severity="error",
        message="Evidence schema/validation is kernel-owned. Use embedded registry.",
    ),
    
    # MD007 - Authority Blocks/Algorithm
    Rule(
        rule_id="MD007",
        name="authority-algorithm",
        description="Authority blocks/algorithm sections are kernel-owned",
        patterns=(
            r"^TRIGGER\s*:",
            r"^ACTION\s*:",
            r"^ALGORITHM\s*:",
            r"^DECISION\s+TREE\s*:",
            r"^IF\b.*\bTHEN\b.*\bELSE\b",
        ),
        severity="error",
        message="Algorithm/trigger/action sections are kernel-owned.",
    ),
    
    # MD008 - Non-normative Guard (for AGENTS.md)
    Rule(
        rule_id="MD008",
        name="non-normative-guard",
        description="AGENTS.md must be non-normative mirror",
        patterns=(
            r".",  # Matches any content - we check for required banner separately
        ),
        severity="error",
        message="AGENTS.md must contain 'non-normative' and 'kernel wins' banner.",
    ),
)

NON_NORMATIVE_REQUIRED = (
    r"\bnon[- ]normative\b",
    r"\bkernel\s+(wins|is\s+ssot|controls)\b",
)


def remove_fenced_blocks(content: str) -> str:
    """Remove fenced code blocks from content."""
    # Remove ``` blocks
    content = re.sub(r"```[\s\S]*?```", "", content)
    # Remove ~~~ blocks
    content = re.sub(r"~~~[\s\S]*?~~~", "", content)
    return content


def remove_html_comments(content: str) -> str:
    """Remove HTML comments from content."""
    return re.sub(r"<!--[\s\S]*?-->", "", content)


def should_check_file(file_path: Path) -> bool:
    """Determine if file should be checked."""
    name = file_path.name.lower()
    # Skip generated files
    if name.startswith("changelog"):
        return False
    if "generated" in name:
        return False
    return True


def check_non_normative_banner(content: str) -> bool:
    """Check if content has required non-normative banner."""
    has_non_normative = any(re.search(p, content, re.IGNORECASE) for p in NON_NORMATIVE_REQUIRED[0:1])
    has_kernel_wins = any(re.search(p, content, re.IGNORECASE) for p in NON_NORMATIVE_REQUIRED[1:])
    return has_non_normative and has_kernel_wins


def lint_file(file_path: Path, rules: Sequence[Rule] = RULES) -> list[Finding]:
    """Lint a single file and return findings."""
    findings: list[Finding] = []
    
    if not should_check_file(file_path):
        return findings
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        findings.append(Finding(
            rule_id="PARSE",
            severity="error",
            file_path=str(file_path),
            line=0,
            column=0,
            match="",
            snippet_hash="",
            context_hash="",
            message=f"Failed to read file: {exc}",
        ))
        return findings
    
    # Special check for AGENTS.md
    if file_path.name.upper() == "AGENTS.MD":
        if not check_non_normative_banner(content):
            findings.append(Finding(
                rule_id="MD008",
                severity="error",
                file_path=str(file_path),
                line=1,
                column=1,
                match="missing non-normative banner",
                snippet_hash="",
                context_hash="",
                message="AGENTS.md must contain 'non-normative' and 'kernel wins' banner.",
            ))
        # Still check other rules, but with exceptions for UI guidance
        # Continue to normal linting
        pass
    
    # Remove fenced blocks and comments
    checkable = remove_fenced_blocks(content)
    checkable = remove_html_comments(checkable)
    
    lines = checkable.split("\n")
    
    for rule in rules:
        if rule.rule_id == "MD008":
            continue  # Handled separately
        
        for i, line in enumerate(lines):
            line_num = i + 1
            
            for pattern in rule.patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if not match:
                    continue
                
                # Check exceptions
                is_exception = False
                for exc_pattern in rule.exceptions:
                    if re.search(exc_pattern, line, re.IGNORECASE):
                        is_exception = True
                        break
                
                if is_exception:
                    continue
                
                # Get context
                prev_line = lines[i - 1] if i > 0 else ""
                next_line = lines[i + 1] if i < len(lines) - 1 else ""
                
                findings.append(Finding(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    file_path=str(file_path),
                    line=line_num,
                    column=match.start() + 1,
                    match=match.group(),
                    snippet_hash=hash_text(line),
                    context_hash=hash_context(prev_line, line, next_line),
                    message=rule.message,
                ))
    
    return findings


def lint_files(
    files: Sequence[Path],
    rules: Sequence[Rule] = RULES,
) -> list[Finding]:
    """Lint multiple files and return all findings."""
    all_findings: list[Finding] = []
    
    for file_path in files:
        findings = lint_file(file_path, rules)
        all_findings.extend(findings)
    
    return all_findings


def discover_md_files(root: Path, exclude: Sequence[str] = ()) -> list[Path]:
    """Discover all .md files in root."""
    files: list[Path] = []
    exclude_set = set(exclude)
    
    for md_file in root.rglob("*.md"):
        rel_path = str(md_file.relative_to(root))
        if any(exc in rel_path for exc in exclude_set):
            continue
        files.append(md_file)
    
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MD-SSOT Linter - Enforces 'MD nur Schienen' rule"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to lint (default: current directory)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Paths to exclude",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit with error code on warnings",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: fail-closed, JSON output, no colors",
    )
    
    args = parser.parse_args()
    
    # Discover files
    files: list[Path] = []
    for path in args.paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(discover_md_files(path, args.exclude))
    
    if not files:
        if args.ci or args.output == "json":
            print(json.dumps({"error": "No files to lint"}))
        else:
            print("No .md files found")
        return 3
    
    # Run linter
    findings = lint_files(files)
    
    # Output
    if args.ci or args.output == "json":
        output = {
            "files_checked": len(files),
            "findings_count": len(findings),
            "findings": [f.to_dict() for f in findings],
        }
        print(json.dumps(output, indent=2))
    else:
        # Text output
        for f in findings:
            print(f"{f.file_path}:{f.line}:{f.column}: {f.severity}: {f.rule_id}: {f.message}")
        
        if findings:
            print(f"\n{len(findings)} finding(s)")
    
    # Exit code
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    
    if errors > 0:
        return 1
    if warnings > 0 and args.fail_on_warnings:
        return 1
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
