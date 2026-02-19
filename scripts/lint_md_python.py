#!/usr/bin/env python3
"""Lint MD files for forbidden patterns.

Ensures MD files contain only "Schienen" (examples/templates), not "Leitplanken"
(execution instructions that should be in kernel).

Categories checked:
1. Execution Control Language - MD must not define WHEN/HOW to execute
2. Authority Language - MD must not define FORBIDDEN/ALLOWED/PERMITTED as policy
3. Mode/Permission Policy - MD must not define mode behavior or permissions

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
    # Execution Control Language
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

# Authority language that should be reviewed (but may be acceptable in context)
AUTHORITY_LANGUAGE_PATTERNS = [
    (r"\bFORBIDDEN\b", "Authority language 'FORBIDDEN' - consider 'Do not output/propose'"),
    (r"\bALLOWED\b", "Authority language 'ALLOWED' - consider output rules"),
    (r"\bPERMITTED\b", "Authority language 'PERMITTED' - consider output rules"),
]

EXECUTION_CONTROL_PATTERNS = [
    (r"MUST execute\s+(?!only|before|after|when|if|deterministic)", "Execution control - kernel SSOT only"),
    (r"continue\.md MUST execute", "Execution flow control in MD - use output description instead"),
    (r"\.py MUST (call|run|execute)", "Execution control in MD - kernel SSOT only"),
    (r"\d+\s+rounds?\s+(completed|mandatory)", "Iteration control in MD - kernel SSOT only"),
    (r"repeat\s+\d+\s+times", "Iteration control in MD - kernel SSOT only"),
    (r"continue\.md (executes|does|triggers)", "Execution flow control in MD"),
]

ALLOWLIST_DIRS = {
    "docs/MD_PYTHON_POLICY.md",  # This document describes the patterns
    "docs/MD_VIOLATION_ANALYSIS.md",  # Documents violations (examples)
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


def lint_md_file(path: Path) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    """Lint a single MD file for forbidden patterns.
    
    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []
    
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    if rel_path in ALLOWLIST_DIRS:
        return errors, warnings
    
    try:
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
    except (OSError, UnicodeDecodeError):
        return errors, warnings
    
    for line_idx, line in enumerate(lines, start=1):
        # Check for dangerous patterns - these are ALWAYS forbidden
        if is_dangerous_execution(line):
            errors.append((line_idx, "Dangerous inline execution (runpy/injection)", line.strip()[:80]))
            continue
        
        # Skip if in fenced code block (it's an example)
        if is_in_fenced_code_block(lines, line_idx - 1):
            continue
        
        # Check for forbidden patterns (errors)
        for pattern, description in FORBIDDEN_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append((line_idx, description, line.strip()[:80]))
        
        # Check for execution control patterns (errors)
        for pattern, description in EXECUTION_CONTROL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append((line_idx, description, line.strip()[:80]))
        
        # Check for authority language (warnings - context matters)
        for pattern, description in AUTHORITY_LANGUAGE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                warnings.append((line_idx, description, line.strip()[:80]))
    
    return errors, warnings


def main() -> int:
    """Lint all MD files in repository."""
    md_files = list(REPO_ROOT.glob("**/*.md"))
    md_files = [f for f in md_files if "node_modules" not in str(f) and ".git" not in str(f)]
    
    all_errors: list[tuple[Path, list[tuple[int, str, str]]]] = []
    all_warnings: list[tuple[Path, list[tuple[int, str, str]]]] = []
    
    for md_file in md_files:
        errors, warnings = lint_md_file(md_file)
        if errors:
            all_errors.append((md_file, errors))
        if warnings:
            all_warnings.append((md_file, warnings))
    
    if not all_errors and not all_warnings:
        print("✓ All MD files compliant (no forbidden patterns)")
        return 0
    
    if all_errors:
        print("✗ MD lint errors found (must fix):\n")
        
        for file_path, errors in all_errors:
            rel_path = file_path.relative_to(REPO_ROOT)
            print(f"  {rel_path}:")
            for line_no, description, preview in errors:
                print(f"    L{line_no}: {description}")
                print(f"           {preview}")
            print()
    
    if all_warnings:
        print("⚠ MD lint warnings (review recommended):\n")
        
        for file_path, warnings in all_warnings:
            rel_path = file_path.relative_to(REPO_ROOT)
            print(f"  {rel_path}:")
            for line_no, description, preview in warnings[:3]:  # Show max 3 per file
                print(f"    L{line_no}: {description}")
            if len(warnings) > 3:
                print(f"    ... and {len(warnings) - 3} more")
            print()
    
    print("See docs/MD_PYTHON_POLICY.md for allowed patterns.")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
