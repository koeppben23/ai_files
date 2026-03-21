#!/usr/bin/env python3
"""
compile_rules.py — Deterministic compiler: rules.md → governance_mandates.schema.json

SSOT source:     governance_content/reference/rules.md
Compiled output: governance_runtime/assets/schemas/governance_mandates.v1.schema.json

Run manually or in CI. Fails if output is stale (rules.md modified but schema not regenerated).
Exit codes: 0=up-to-date or regenerated, 1=stale/mismatch, 2=error
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).absolute().parents[1]
_RULES_MD = _REPO_ROOT / "governance_content" / "reference" / "rules.md"
_SCHEMA_OUT = _REPO_ROOT / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"
_SCHEMA_VERSION = "1.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract_code_block(content: str, heading_pattern: str) -> str | None:
    """Extract content from a fenced code block under a given heading."""
    escaped = re.escape(heading_pattern)
    match = re.search(
        rf"(?:^|\n)(###?\s+{escaped}.*?)\n+```\s*\n(.*?)\n```",
        content,
        re.DOTALL | re.MULTILINE,
    )
    if match:
        return match.group(2).strip()
    return None


def _parse_mandate(text: str) -> dict:
    """Parse a mandate code-block text into a structured dict."""
    if not text:
        return {}
    lines = text.splitlines()
    sections: dict[str, list[str] | str] = {}
    current_section = "root"
    current_items: list[str] = []
    in_code_block = False
    code_buffer: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            if in_code_block:
                sections[current_section] = "\n".join(code_buffer).strip()
                code_buffer = []
                in_code_block = False
                current_section = "root"
                current_items = []
            else:
                if current_items:
                    sections[current_section] = current_items
                    current_items = []
                in_code_block = True
            continue

        if in_code_block:
            code_buffer.append(raw_line)
            continue

        if not stripped:
            if current_items:
                sections[current_section] = current_items
                current_items = []
            continue

        # Section header (line ending with nothing else, or followed by items)
        if re.match(r"^[A-Z][A-Za-z ]+(\s*)$", stripped) and not stripped.startswith("-"):
            if current_items and current_section != "root":
                sections[current_section] = current_items
                current_items = []
            current_section = stripped.lower().replace(" ", "_")
            continue

        # List item
        if stripped.startswith("- ") or stripped.startswith("* "):
            current_items.append(stripped[2:])
        elif re.match(r"^\d+\.\s+", stripped):
            current_items.append(re.sub(r"^\d+\.\s+", "", stripped))
        else:
            current_items.append(stripped)

    if current_items and current_section != "root":
        sections[current_section] = current_items

    return sections


def _section_to_list(value: str | list | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [v.strip() for v in str(value).split("\n") if v.strip()]


def _build_lens(name: str, raw: str | list | None) -> dict:
    items = _section_to_list(raw)
    ask_items = [i for i in items if i.startswith("Ask:")]
    body_items = [i for i in items if not i.startswith("Ask:")]
    return {
        "name": name,
        "description": " ".join(body_items[:1]) if body_items else "",
        "body": body_items,
        "ask": [a.replace("Ask:", "").strip() for a in ask_items],
    }


def _compile_review_mandate(text: str) -> dict:
    parsed = _parse_mandate(text)
    lenses = [
        _build_lens("Correctness", parsed.get("1_correctness", "")),
        _build_lens("Contract integrity", parsed.get("2_contract_integrity", "")),
        _build_lens("Architecture", parsed.get("3_architecture", "")),
        _build_lens("Regression risk", parsed.get("4_regression_risk", "")),
        _build_lens("Testing quality", parsed.get("5_testing_quality", "")),
        _build_lens("Security", parsed.get("6_security", "")),
        _build_lens("Concurrency", parsed.get("7_concurrency", "")),
        _build_lens("Performance", parsed.get("8_performance", "")),
        _build_lint_or_portability(parsed.get("9_portability", "")),
        _build_lens("Business logic", parsed.get("10_business_logic", "")),
    ]

    adversarial_raw = parsed.get("adversarial_method", [])
    if isinstance(adversarial_raw, list):
        adversarial = adversarial_raw
    elif isinstance(adversarial_raw, str):
        adversarial = [l.strip() for l in adversarial_raw.splitlines() if l.strip()]
    else:
        adversarial = []

    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "governance_content/reference/rules.md",
        "compiled_at": _now_iso(),
        "role": "falsification-first reviewer",
        "core_posture": _section_to_list(parsed.get("core_posture", "")),
        "evidence_rule": _section_to_list(parsed.get("evidence_rule", "")),
        "primary_objectives": _section_to_list(parsed.get("primary_review_objectives", "")),
        "review_lenses": lenses,
        "adversarial_method": adversarial,
        "output_contract": {
            "verdict": "approve | changes_requested",
            "findings": [
                {
                    "severity": "critical | high | medium | low",
                    "type": "defect | risk | contract-drift | test-gap | improvement",
                    "location": "exact file/function/area",
                    "evidence": "what specifically proves the finding",
                    "impact": "what can break or become unsafe",
                    "fix": "the smallest credible correction",
                }
            ],
            "regression_assessment": "what existing behavior is most at risk if this merges",
            "test_assessment": "what tests are missing, weak, misleading, or sufficient",
        },
        "decision_rules": _section_to_list(parsed.get("decision_rules", "")),
        "style_rules": _section_to_list(parsed.get("style_rules", "")),
        "governance_addendum": _section_to_list(parsed.get("governance_addendum", "")),
    }


def _build_lint_or_portability(raw: str | list | None) -> dict:
    return _build_lens("Portability", raw)


def _compile_developer_mandate(text: str) -> dict:
    parsed = _parse_mandate(text)
    lenses = [
        _build_lens("Correctness", parsed.get("1_correctness", "")),
        _build_lens("Contract integrity", parsed.get("2_contract_integrity", "")),
        _build_lens("Authority and ownership", parsed.get("3_authority_and_ownership", "")),
        _build_lens("Minimality and blast radius", parsed.get("4_minimality_and_blast_radius", "")),
        _build_lens("Testing quality", parsed.get("5_testing_quality", "")),
        _build_lens("Operability", parsed.get("6_operability", "")),
        _build_lens("Security and trust boundaries", parsed.get("7_security_and_trust_boundaries", "")),
        _build_lens("Concurrency", parsed.get("8_concurrency", "")),
        _build_lens("Performance", parsed.get("9_performance", "")),
        _build_lens("Portability", parsed.get("10_portability", "")),
        _build_lens("Migration and compatibility", parsed.get("11_migration_and_compatibility", "")),
    ]

    authoring_method_raw = parsed.get("authoring_method", [])
    if isinstance(authoring_method_raw, list):
        authoring_method = authoring_method_raw
    elif isinstance(authoring_method_raw, str):
        authoring_method = [l.strip() for l in authoring_method_raw.splitlines() if l.strip()]
    else:
        authoring_method = []

    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "governance_content/reference/rules.md",
        "compiled_at": _now_iso(),
        "role": "contract-first developer",
        "core_posture": _section_to_list(parsed.get("core_posture", "")),
        "evidence_rule": _section_to_list(parsed.get("evidence_rule", "")),
        "primary_authoring_objectives": _section_to_list(parsed.get("primary_authoring_objectives", "")),
        "authoring_lenses": lenses,
        "authoring_method": authoring_method,
        "output_contract": {
            "objective": "The requested outcome in one precise sentence",
            "governing_evidence": "exact contracts, specs, files, or repository rules that govern the change",
            "touched_surface": "files/modules/commands/configs/docs/tests changed",
            "change_summary": "minimal behavioral change made",
            "contract_and_authority_check": "SSOT/authority preservation, fallback handling, ambiguity",
            "test_evidence": "what was tested, risky paths covered, what remains unproven",
            "regression_assessment": "existing behavior most likely to regress",
            "residual_risks": "uncertain, deferred, or requiring follow-up items",
        },
        "decision_rules": _section_to_list(parsed.get("decision_rules", "")),
        "style_rules": _section_to_list(parsed.get("style_rules", "")),
        "governance_addendum": _section_to_list(parsed.get("governance_addendum", "")),
    }


def compile_rules() -> dict:
    """Compile rules.md into a structured JSON schema."""
    if not _RULES_MD.exists():
        raise FileNotFoundError(f"SSOT not found: {_RULES_MD}")

    content = _RULES_MD.read_text(encoding="utf-8")
    review_text = _extract_code_block(content, "Review mandate")
    developer_text = _extract_code_block(content, "Authoring mandate")

    if not review_text:
        raise ValueError("Review mandate not found in rules.md")
    if not developer_text:
        raise ValueError("Authoring mandate not found in rules.md")

    review_mandate = _compile_review_mandate(review_text)
    developer_mandate = _compile_developer_mandate(developer_text)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "governance/schemas/governance_mandates.v1.schema.json",
        "title": "Governance Mandates Schema",
        "description": "Compiled machine-readable representation of REVIEW and DEVELOPER mandates from rules.md SSOT.",
        "type": "object",
        "required": ["schema_version", "source_digest", "review_mandate", "developer_mandate"],
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "const": _SCHEMA_VERSION},
            "source": {"type": "string", "const": str(_RULES_MD.relative_to(_REPO_ROOT))},
            "source_digest": {"type": "string", "description": "SHA-256 of rules.md at compile time"},
            "compiled_at": {"type": "string", "format": "date-time"},
            "review_mandate": {"type": "object", "description": "Compiled Review mandate"},
            "developer_mandate": {"type": "object", "description": "Compiled Developer/Authoring mandate"},
        },
        "review_mandate": review_mandate,
        "developer_mandate": developer_mandate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = __import__("argparse").ArgumentParser(description="Compile rules.md → governance_mandates.schema.json")
    parser.add_argument("--check", action="store_true", help="Exit 1 if schema is stale (rules.md modified but schema not regenerated)")
    parser.add_argument("--force", action="store_true", help="Regenerate schema even if up-to-date")
    args = parser.parse_args(argv or sys.argv[1:])

    if not _RULES_MD.exists():
        print(f"ERROR: SSOT not found: {_RULES_MD}", file=sys.stderr)
        return 2

    source_digest = _digest_file(_RULES_MD)

    if _SCHEMA_OUT.exists():
        try:
            existing = json.loads(_SCHEMA_OUT.read_text(encoding="utf-8"))
            existing_digest = existing.get("source_digest", "")
            if not args.force and existing_digest == source_digest:
                print(f"OK: {relative(_SCHEMA_OUT)} is up-to-date (source_digest matches)")
                return 0
            if args.check and existing_digest != source_digest:
                print(
                    f"STALE: {relative(_SCHEMA_OUT)} source_digest mismatch.\n"
                    f"  Expected: {source_digest}\n"
                    f"  Got:      {existing_digest}\n"
                    f"  Run: python scripts/compile_rules.py to regenerate.",
                    file=sys.stderr,
                )
                return 1
        except (json.JSONDecodeError, KeyError):
            pass

    schema = compile_rules()
    schema["source_digest"] = source_digest
    schema["compiled_at"] = _now_iso()

    _SCHEMA_OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(schema, ensure_ascii=True, indent=2) + "\n"
    _SCHEMA_OUT.write_text(text, encoding="utf-8")
    print(f"Compiled: {relative(_SCHEMA_OUT)} ({len(text):,} bytes, source_digest={source_digest[:16]}...)")
    return 0


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
