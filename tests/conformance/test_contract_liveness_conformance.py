from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.util import REPO_ROOT, get_docs_path


CONTRACTS_DIR = get_docs_path() / "contracts"


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    assert m, f"No YAML frontmatter found in {path}"
    return yaml.safe_load(m.group(1))


def _contracts() -> list[Path]:
    return sorted(CONTRACTS_DIR.glob("*.md"))


@pytest.mark.conformance
def test_no_planned_or_tbd_in_contract_frontmatter() -> None:
    offenders: list[str] = []
    for contract in _contracts():
        fm = _parse_frontmatter(contract)
        rel = contract.relative_to(REPO_ROOT).as_posix()
        if str(fm.get("status", "")).strip().lower() == "planned":
            offenders.append(f"{rel}: status=planned")
        if str(fm.get("effective_version", "")).strip().lower() == "tbd":
            offenders.append(f"{rel}: effective_version=TBD")
        if str(fm.get("conformance_suite", "")).strip().lower() == "tbd":
            offenders.append(f"{rel}: conformance_suite=TBD")
    assert not offenders, f"planned/TBD contract metadata remains: {offenders}"


@pytest.mark.conformance
def test_active_contracts_have_real_conformance_suites() -> None:
    offenders: list[str] = []
    for contract in _contracts():
        fm = _parse_frontmatter(contract)
        status = str(fm.get("status", "")).strip().lower()
        if status != "active":
            continue
        rel = contract.relative_to(REPO_ROOT).as_posix()
        suite = str(fm.get("conformance_suite", "")).strip()
        if not suite or suite.lower() == "archived":
            offenders.append(f"{rel}: active contract missing concrete conformance_suite")
            continue
        suite_path = REPO_ROOT / suite
        if not suite_path.is_file():
            offenders.append(f"{rel}: conformance_suite file missing ({suite})")
    assert not offenders, f"active contract suite wiring invalid: {offenders}"


@pytest.mark.conformance
def test_archived_contracts_use_archived_markers() -> None:
    offenders: list[str] = []
    for contract in _contracts():
        fm = _parse_frontmatter(contract)
        status = str(fm.get("status", "")).strip().lower()
        if status != "archived":
            continue
        rel = contract.relative_to(REPO_ROOT).as_posix()
        if str(fm.get("effective_version", "")).strip().lower() != "archived":
            offenders.append(f"{rel}: archived contract must set effective_version=archived")
        if str(fm.get("conformance_suite", "")).strip().lower() != "archived":
            offenders.append(f"{rel}: archived contract must set conformance_suite=archived")
    assert not offenders, f"archived contract markers invalid: {offenders}"


@pytest.mark.conformance
def test_v_next_contracts_are_not_live() -> None:
    offenders: list[str] = []
    for contract in _contracts():
        fm = _parse_frontmatter(contract)
        version = str(fm.get("version", "")).strip().lower()
        if version != "v_next":
            continue
        rel = contract.relative_to(REPO_ROOT).as_posix()
        if str(fm.get("status", "")).strip().lower() == "active":
            offenders.append(f"{rel}: v_next contract cannot be active")
    assert not offenders, f"v_next contracts still live: {offenders}"


@pytest.mark.conformance
def test_install_layout_contract_pairing_is_finalized() -> None:
    current = _parse_frontmatter(CONTRACTS_DIR / "install-layout-contract.v_current.md")
    v_next = _parse_frontmatter(CONTRACTS_DIR / "install-layout-contract.v_next.md")
    migration = _parse_frontmatter(CONTRACTS_DIR / "install-layout-migration.v1.md")

    assert str(current.get("status", "")).lower() == "active"
    assert str(current.get("conformance_suite", "")) == "tests/conformance/test_layout_conformance.py"

    assert str(v_next.get("status", "")).lower() == "archived"
    assert str(v_next.get("effective_version", "")).lower() == "archived"
    assert str(v_next.get("conformance_suite", "")).lower() == "archived"

    assert str(migration.get("status", "")).lower() == "archived"
    assert str(migration.get("effective_version", "")).lower() == "archived"
    assert str(migration.get("conformance_suite", "")).lower() == "archived"
