#!/usr/bin/env python3
"""Lint MD files for forbidden Python execution patterns.

Ensures MD files contain only "Schienen" (examples/templates), not "Leitplanken"
(execution instructions that should be in kernel).

Usage:
    python3 scripts/lint_md_python.py

Exit codes:
    0 - All MD files compliant
    1 - Violations found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATTERNS = [
    (r"^\s*!\`\$\{PYTHON_COMMAND\}", "Inline Python execution (OpenCode command injection)"),
    (r"^\s*!\`python", "Inline Python execution"),
    (r"python\s+-c\s+\"import\s+runpy", "runpy inline execution"),
    (r"subprocess\.", "subprocess call"),
    (r"pip\s+install", "pip install instruction"),
    (r"curl\s+", "curl command"),
    (r"wget\s+", "wget command"),
    (r"os\.system\(", "os.system call"),
    (r"eval\(", "eval call"),
    (r"exec\(", "exec call"),
]

ALLOWLIST_DIRS = {
    "docs/MD_PYTHON_POLICY.md",  # This document describes the patterns
    "docs/CLEAN_ARCHITECTURE_VIOLATION.md",  # Documents violations (examples)
}

EXEMPTION_PATTERNS = [
    r"#\s*EXAMPLE\s+ONLY",
    r"#\s*DO\s+NOT\s+EXECUTE",
    r"```\w*\s*$",  # Start of fenced code block
]


def is_in_fenced_code_block(lines: list[str], line_idx: int) -> bool:
    """Check if line is inside any fenced code block."""
    in_block = False
    
    for i, line in enumerate(lines):
        if i > line_idx:
            break
        if re.match(r"^```\w*$", line):
            in_block = not in_block
    
    return in_block


def is_in_example_block(lines: list[str], line_idx: int) -> bool:
    """Check if line is inside a fenced code block marked as example."""
    in_block = False
    block_start = -1
    
    for i, line in enumerate(lines):
        if i > line_idx:
            break
        if re.match(r"^```\w*$", line):
            if not in_block:
                in_block = True
                block_start = i
            else:
                in_block = False
                block_start = -1
    
    if not in_block or block_start < 0:
        return False
    
    # Check if block has EXAMPLE ONLY marker
    for i in range(block_start, min(block_start + 5, len(lines))):
        if re.match(r"#\s*EXAMPLE\s+ONLY", lines[i], re.IGNORECASE):
            return True
        if re.match(r"#\s*DO\s+NOT\s+EXECUTE", lines[i], re.IGNORECASE):
            return True
    
    return False


def is_dangerous_execution(line: str) -> bool:
    """Check if line contains dangerous execution patterns that are forbidden even in examples."""
    dangerous_patterns = [
        r"python\s+-c\s+\"import\s+runpy",
        r"import\s+runpy",
        r"^\s*!\`\$\{PYTHON_COMMAND\}",
        r"^\s*!\`python",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def lint_md_file(path: Path) -> list[tuple[int, str, str]]:
    """Lint a single MD file for forbidden patterns."""
    violations = []
    
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    if rel_path in ALLOWLIST_DIRS:
        return violations
    
    try:
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
    except (OSError, UnicodeDecodeError):
        return violations
    
    for line_idx, line in enumerate(lines, start=1):
        # Check for dangerous patterns - these are ALWAYS forbidden
        if is_dangerous_execution(line):
            violations.append((line_idx, "Dangerous inline execution (runpy/injection)", line.strip()[:80]))
            continue
        
        # Check for other forbidden patterns
        for pattern, description in FORBIDDEN_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                # Skip if in fenced code block (it's an example)
                if is_in_fenced_code_block(lines, line_idx - 1):
                    continue
                
                violations.append((line_idx, description, line.strip()[:80]))
    
    return violations


def main() -> int:
    """Lint all MD files in repository."""
    md_files = list(REPO_ROOT.glob("**/*.md"))
    md_files = [f for f in md_files if "node_modules" not in str(f) and ".git" not in str(f)]
    
    all_violations: list[tuple[Path, list[tuple[int, str, str]]]] = []
    
    for md_file in md_files:
        violations = lint_md_file(md_file)
        if violations:
            all_violations.append((md_file, violations))
    
    if not all_violations:
        print("✓ All MD files compliant (no forbidden execution patterns)")
        return 0
    
    print("✗ MD Python lint violations found:\n")
    
    for file_path, violations in all_violations:
        rel_path = file_path.relative_to(REPO_ROOT)
        print(f"  {rel_path}:")
        for line_no, description, preview in violations:
            print(f"    L{line_no}: {description}")
            print(f"           {preview}")
        print()
    
    print("See docs/MD_PYTHON_POLICY.md for allowed patterns.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
