from __future__ import annotations

import re
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text


@pytest.mark.governance
def test_required_files_present():
    required = [
        "master.md",
        "rules.md",
        "start.md",
        "SESSION_STATE_SCHEMA.md",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    assert not missing, f"Missing: {missing}"


@pytest.mark.governance
def test_blocked_consistency_schema_vs_master():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    master = read_text(REPO_ROOT / "master.md")

    s = set(re.findall(r"BLOCKED-[A-Z-]+", schema))
    m = set(re.findall(r"BLOCKED-[A-Z-]+", master))

    missing_in_master = s - m
    missing_in_schema = m - s
    assert not missing_in_master, f"Missing in master: {sorted(missing_in_master)}"
    assert not missing_in_schema, f"Missing in schema: {sorted(missing_in_schema)}"


@pytest.mark.governance
def test_profiles_use_canonical_blocked_codes():
    forbidden = {
        "BLOCKED-TEMPLATES-MISSING",
        "BLOCKED-KAFKA-TEMPLATES-MISSING",
    }
    profile_files = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert profile_files, "No profile rulebooks found under profiles/rules*.md"

    offenders: list[str] = []
    for p in profile_files:
        t = read_text(p)
        hits = sorted([code for code in forbidden if code in t])
        if hits:
            offenders.append(f"{p.relative_to(REPO_ROOT)} -> {hits}")

    assert not offenders, "Found non-canonical BLOCKED codes in profiles:\n" + "\n".join([f"- {o}" for o in offenders])


@pytest.mark.governance
def test_master_min_template_lists_extended_phase_values():
    master = read_text(REPO_ROOT / "master.md")
    required_tokens = [
        "1.1-Bootstrap",
        "1.2-ProfileDetection",
        "1.3-CoreRulesActivation",
        "2.1-DecisionPack",
        "5.6",
    ]
    missing = [t for t in required_tokens if t not in master]
    assert not missing, "master MIN template missing phase tokens:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_master_bootstrap_fields_match_schema_contract():
    master = read_text(REPO_ROOT / "master.md")
    required = ["Bootstrap:", "Present:", "Satisfied:", "Evidence:"]
    missing = [k for k in required if k not in master]
    assert not missing, "master bootstrap section missing required schema fields:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_schema_phase4_ticket_record_declares_must_include():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    assert "When Phase 4 planning is produced, the workflow MUST include:" in schema


@pytest.mark.governance
def test_gate_scorecard_and_review_of_review_contract_present():
    rules = read_text(REPO_ROOT / "rules.md")
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    assert "### 7.7.2 Gate Review Scorecard" in rules
    assert "### 7.7.4 Review-of-Review Consistency Check" in rules
    assert "Gate Review Scorecard (binding):" in master
    assert "review-of-review" in master
    assert "GateScorecards" in schema
