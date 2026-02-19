#!/usr/bin/env python3
"""Fix authority language patterns in MD files.

Converts authority language to output rules where appropriate:
- "is forbidden" → "Do not ..."
- "is not allowed" → "Do not ..." 
- "is permitted" → "may" or rephrase

Usage:
    python3 scripts/fix_md_authority_language.py --dry-run
    python3 scripts/fix_md_authority_language.py --apply
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

# Patterns that should be fixed
FIX_PATTERNS = [
    # "is forbidden" → "Do not"
    (r"(\w[^.]*?)\s+is\s+forbidden(?!\s+from)", r"Do not \1"),
    (r"(\w[^.]*?)\s+remains\s+forbidden", r"Do not \1"),
    
    # "X is not allowed" → "Do not X"
    (r"(\w[^.]*?)\s+is\s+not\s+allowed", r"Do not \1"),
    
    # "X is only permitted if" → "X may only be done if"
    (r"(\w[^.]*?)\s+is\s+only\s+permitted\s+if", r"\1 may only be done if"),
    
    # "is permitted" → "may"
    (r"(\w[^.]*?)\s+is\s+permitted", r"\1 may be done"),
]

# Files to skip (documentation about patterns)
SKIP_FILES = {
    "docs/MD_VIOLATION_ANALYSIS.md",
    "docs/MD_PYTHON_POLICY.md",
    "CHANGELOG.md",  # Historical, don't modify
}


def should_skip(path: Path) -> bool:
    rel_path = path.relative_to(REPO_ROOT).as_posix()
    return rel_path in SKIP_FILES


def is_in_code_block(lines: list[str], line_idx: int) -> bool:
    """Check if line is inside a fenced code block."""
    in_block = False
    for i, line in enumerate(lines):
        if i > line_idx:
            break
        if re.match(r"^```\w*$", line):
            in_block = not in_block
    return in_block


def is_table_row(line: str) -> bool:
    """Check if line is part of a markdown table."""
    return line.strip().startswith("|") and "|" in line[1:]


def fix_line(line: str) -> tuple[str, bool]:
    """Apply fixes to a line. Returns (fixed_line, was_fixed)."""
    original = line
    
    # Skip table rows - they're descriptive, not authoritative
    if is_table_row(line):
        return line, False
    
    # Skip lines that are section headers
    if line.strip().startswith("#"):
        return line, False
    
    for pattern, replacement in FIX_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            line = re.sub(pattern, replacement, line, flags=re.IGNORECASE)
    
    return line, line != original


def process_file(path: Path, dry_run: bool = True) -> int:
    """Process a single file. Returns number of fixes."""
    if should_skip(path):
        return 0
    
    try:
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
    except (OSError, UnicodeDecodeError):
        return 0
    
    fixes = 0
    new_lines = []
    
    for i, line in enumerate(lines):
        if is_in_code_block(lines, i):
            new_lines.append(line)
            continue
        
        fixed_line, was_fixed = fix_line(line)
        if was_fixed:
            fixes += 1
            if dry_run:
                print(f"  L{i+1}: {line.strip()[:60]}")
                print(f"     → {fixed_line.strip()[:60]}")
        new_lines.append(fixed_line)
    
    if not dry_run and fixes > 0:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    
    return fixes


def main() -> int:
    dry_run = "--apply" not in sys.argv
    
    if dry_run:
        print("DRY RUN - no changes will be made\n")
    else:
        print("APPLYING FIXES\n")
    
    md_files = list(REPO_ROOT.glob("**/*.md"))
    md_files = [f for f in md_files if "node_modules" not in str(f) and ".git" not in str(f)]
    
    total_fixes = 0
    files_with_fixes = []
    
    for md_file in sorted(md_files):
        fixes = process_file(md_file, dry_run)
        if fixes > 0:
            rel_path = md_file.relative_to(REPO_ROOT)
            files_with_fixes.append((rel_path, fixes))
            total_fixes += fixes
    
    print(f"\n{'Would fix' if dry_run else 'Fixed'} {total_fixes} instances in {len(files_with_fixes)} files:")
    for path, count in files_with_fixes:
        print(f"  {count:2d} | {path}")
    
    if dry_run:
        print("\nRun with --apply to make changes")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
