#!/usr/bin/env python3
"""
Rulebook MD to YAML Extractor

Extracts structured rulebook data from Markdown files for conversion to YAML.
This is a bootstrap tool - output requires manual curation before schema validation.
"""

from __future__ import annotations

import json
import re
import sys
import yaml
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class Metadata:
    id: str
    name: str
    version: str = "1.0"
    status: str = "active"


@dataclass
class Condition:
    field: str
    operator: str
    value: str | bool | int | float | None


@dataclass
class Activation:
    type: str
    conditions: list[Condition] = field(default_factory=list)


@dataclass
class PhaseIntegration:
    phases: list[str]
    required_outputs: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)


@dataclass
class EvidenceContract:
    required_artifacts: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)
    acceptance_rules: list[dict] = field(default_factory=list)


@dataclass
class CodeBlock:
    language: Optional[str] = None
    code: str = ""


@dataclass
class Pattern:
    id: str
    title: str
    enforces: list[str] = field(default_factory=list)
    code_example: Optional[CodeBlock] = None
    rationale: Optional[str] = None


@dataclass
class AntiPattern:
    id: str
    title: str
    detects: list[str] = field(default_factory=list)
    recovery: str = ""


@dataclass
class DecisionTree:
    id: str
    title: str = ""
    root: dict = field(default_factory=dict)


@dataclass
class WarningCode:
    code: str
    triggers: list[str] = field(default_factory=list)
    recovery: Optional[str] = None


@dataclass
class TypedReference:
    id: str
    target: str
    type: str


@dataclass
class Rulebook:
    kind: str
    metadata: Metadata
    precedence: Optional[dict] = None
    activation: Optional[Activation] = None
    phase_integration: Optional[PhaseIntegration] = None
    evidence_contract: Optional[EvidenceContract] = None
    patterns: list[Pattern] = field(default_factory=list)
    anti_patterns: list[AntiPattern] = field(default_factory=list)
    decision_trees: list[DecisionTree] = field(default_factory=list)
    verification_commands: list[dict] = field(default_factory=list)
    warning_codes: list[WarningCode] = field(default_factory=list)
    references: list[TypedReference] = field(default_factory=list)


def detect_kind(file_path: Path) -> str:
    """Detect if this is a core or profile rulebook."""
    name = file_path.stem.lower()
    if name in ("master", "rules", "bootstrap"):
        return "core"
    return "profile"


def detect_binding(header_line: str) -> bool:
    """Detect if a section is binding."""
    return "(binding)" in header_line.lower() or "(mandatory)" in header_line.lower()


def extract_phase_from_text(text: str) -> list[str]:
    """Extract phase references and convert to phase_ID format."""
    phases = []
    patterns = [
        (r'Phase\s*(\d+(?:\.\d+)?)', r'phase_\1'),
    ]
    
    for pattern, replacement in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            phase_id = match.replace('.', '_')
            if not phase_id.endswith('_'):
                phase_id = phase_id + "_"
            phases.append(f"phase_{phase_id.rstrip('_')}")
    
    return list(set(phases))


def extract_patterns(content: str) -> list[Pattern]:
    """Extract PAT-* patterns from content."""
    patterns = []
    pattern_regex = r'###\s+(PAT-[A-Z0-9-]+):\s+(.+?)(?=\n###|\n##|\Z)'
    
    for match in re.finditer(pattern_regex, content, re.DOTALL):
        pat_id = match.group(1)
        section = match.group(2)
        
        title_match = re.search(r'\*\\*([^\*]+)\\*\\*', section)
        title = title_match.group(1).strip() if title_match else pat_id
        
        code_examples = []
        code_blocks = re.findall(r'```(\w+)?\n(.*?)```', section, re.DOTALL)
        for lang, code in code_blocks:
            code_examples.append(CodeBlock(language=lang or "text", code=code.strip()))
        
        rationale = ""
        rationale_match = re.search(r'\*\*Why:\*\*(.+?)(?=\n|$)', section, re.DOTALL)
        if rationale_match:
            rationale = rationale_match.group(1).strip()
        
        patterns.append(Pattern(
            id=pat_id,
            title=title,
            enforces=[],
            code_example=code_examples[0] if code_examples else None,
            rationale=rationale
        ))
    
    return patterns


def extract_anti_patterns(content: str) -> list[AntiPattern]:
    """Extract AP-* anti-patterns from content."""
    anti_patterns = []
    pattern_regex = r'###\s+(AP-[A-Z0-9-]+):\s+(.+?)(?=\n###|\n##|\Z)'
    
    for match in re.finditer(pattern_regex, content, re.DOTALL):
        ap_id = match.group(1)
        section = match.group(2)
        
        title_match = re.search(r'\*\*([^\*]+)\*\*', section)
        title = title_match.group(1).strip() if title_match else ap_id
        
        detection = ""
        detection_match = re.search(r'\*\*Detection:\*\*(.+?)(?=\n\*\*|$)', section, re.DOTALL)
        if detection_match:
            detection = detection_match.group(1).strip()
        
        recovery = ""
        recovery_match = re.search(r'\*\*Recovery:\*\*(.+?)(?=\n\*\*|$)', section, re.DOTALL)
        if recovery_match:
            recovery = recovery_match.group(1).strip()
        
        why = ""
        why_match = re.search(r'\*\*Why it is harmful:\*\*(.+?)(?=\n\*\*|$)', section, re.DOTALL)
        if why_match:
            why = why_match.group(1).strip()
        
        anti_patterns.append(AntiPattern(
            id=ap_id,
            title=title,
            detects=[detection] if detection else [],
            recovery=recovery
        ))
    
    return anti_patterns


def extract_decision_trees(content: str) -> list[DecisionTree]:
    """Extract DT-* decision trees from content."""
    trees = []
    pattern_regex = r'###\s+(DT-[A-Z0-9-]+):\s+(.+?)(?=\n###|\n##|\Z)'
    
    for match in re.finditer(pattern_regex, content, re.DOTALL):
        dt_id = match.group(1)
        section = match.group(2)
        
        title_match = re.search(r'\*\*([^\*]+)\*\*', section)
        title = title_match.group(1).strip() if title_match else dt_id
        
        trees.append(DecisionTree(id=dt_id, title=title))
    
    return trees


def extract_warning_codes(content: str) -> list[WarningCode]:
    """Extract warning codes from content."""
    codes = []
    pattern_regex = r'(WARN-[A-Z0-9-]+)'
    
    for match in re.finditer(pattern_regex, content):
        code = match.group(1)
        if not any(c.code == code for c in codes):
            codes.append(WarningCode(code=code, triggers=[]))
    
    return codes


def extract_references(content: str) -> list[TypedReference]:
    """Extract references to other rulebooks."""
    refs = []
    ref_patterns = [
        r'rules\.(\w+(?:-\w+)*)\.md',
        r'`([^`]+\.addon\.yml)`',
        r'`([^`]+\.schema\.json)`',
    ]
    
    for pattern in ref_patterns:
        for match in re.finditer(pattern, content):
            target = match.group(1)
            ref_type = "rulebook" if ".md" in pattern else "schema"
            refs.append(TypedReference(
                id=f"ref_{len(refs) + 1}",
                target=target,
                type=ref_type
            ))
    
    return refs


def extract_from_md(md_path: Path) -> dict:
    """Main extraction function."""
    content = md_path.read_text(encoding="utf-8")
    
    kind = detect_kind(md_path)
    
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    name = title_match.group(1).strip() if title_match else md_path.stem
    
    metadata = Metadata(
        id=f"{'core' if kind == 'core' else 'profile'}.{md_path.stem.replace('rules.', '')}",
        name=name,
        version="1.0",
        status="active"
    )
    
    rulebook = {
        "kind": kind,
        "metadata": asdict(metadata),
    }
    
    phases = extract_phase_from_text(content)
    if phases:
        rulebook["phase_integration"] = {
            "phases": list(set(phases)),
            "required_outputs": [],
            "required_checks": []
        }
    
    patterns = extract_patterns(content)
    if patterns:
        rulebook["patterns"] = [asdict(p) for p in patterns]
    
    anti_patterns = extract_anti_patterns(content)
    if anti_patterns:
        rulebook["anti_patterns"] = [asdict(ap) for ap in anti_patterns]
    
    decision_trees = extract_decision_trees(content)
    if decision_trees:
        rulebook["decision_trees"] = [asdict(dt) for dt in decision_trees]
    
    warning_codes = extract_warning_codes(content)
    if warning_codes:
        rulebook["warning_codes"] = [asdict(wc) for wc in warning_codes]
    
    references = extract_references(content)
    if references:
        rulebook["references"] = [asdict(r) for r in references]
    
    return rulebook


def main(argv: list[str] | None = None) -> int:
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract rulebook structure from MD files.")
    parser.add_argument("input", type=Path, help="Input MD file")
    parser.add_argument("-o", "--output", type=Path, help="Output YAML file")
    parser.add_argument("--validate", action="store_true", help="Validate against schema")
    
    args = parser.parse_args(argv)
    
    if not args.input.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        return 1
    
    extracted = extract_from_md(args.input)
    
    output = args.output or args.input.with_suffix(".yml")
    
    yaml_content = yaml.dump(
        extracted,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000
    )
    
    output.write_text(yaml_content, encoding="utf-8")
    print(f"Extracted to: {output}")
    
    if args.validate:
        try:
            import jsonschema
            schema = json.loads(Path("schemas/rulebook.schema.json").read_text(encoding="utf-8"))
            jsonschema.validate(extracted, schema)
            print("Schema validation: PASSED")
        except ImportError:
            print("WARNING: jsonschema not installed, skipping validation")
        except Exception as e:
            print(f"Schema validation: FAILED - {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
