from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "validate_rulebook.py"
RULEBOOK_SCHEMA = REPO_ROOT / "schemas" / "rulebook.schema.json"


def _import_validate_module():
    spec = importlib.util.spec_from_file_location("validate_rulebook", str(VALIDATE_SCRIPT))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rulebook_yaml(pass_criteria_block: str) -> str:
    return (
        "kind: profile\n"
        "metadata:\n"
        "  id: profile.schema-contract-test\n"
        "  name: Schema Contract Test\n"
        "  version: '1.0'\n"
        "  schema_version: '1.2.0'\n"
        "  status: deprecated\n"
        "phase_exit_contract:\n"
        "  - phase: phase_5\n"
        "    pass_criteria:\n"
        f"{pass_criteria_block}"
    )


def _validate_text(tmp_path: Path, yaml_text: str) -> list[str]:
    module = _import_validate_module()
    schema = json.loads(RULEBOOK_SCHEMA.read_text(encoding="utf-8"))
    path = tmp_path / "contract-test.yml"
    path.write_text(yaml_text, encoding="utf-8")
    return module.validate_file(path, schema)


@pytest.mark.governance
def test_pass_criterion_rejects_empty_criterion_key(tmp_path: Path) -> None:
    issues = _validate_text(
        tmp_path,
        _rulebook_yaml(
            "      - criterion_key: ''\n"
            "        critical: true\n"
            "        artifact_kind: test_quality_gate\n"
        ),
    )
    assert any("criterion_key" in issue for issue in issues)


@pytest.mark.governance
def test_pass_criterion_rejects_empty_artifact_kind(tmp_path: Path) -> None:
    issues = _validate_text(
        tmp_path,
        _rulebook_yaml(
            "      - criterion_key: quality\n"
            "        critical: true\n"
            "        artifact_kind: ''\n"
        ),
    )
    assert any("artifact_kind" in issue for issue in issues)


@pytest.mark.governance
def test_pass_criterion_rejects_negative_threshold(tmp_path: Path) -> None:
    issues = _validate_text(
        tmp_path,
        _rulebook_yaml(
            "      - criterion_key: quality\n"
            "        critical: true\n"
            "        artifact_kind: test_quality_gate\n"
            "        threshold: -1\n"
        ),
    )
    assert any("threshold" in issue and "minimum" in issue for issue in issues)


@pytest.mark.governance
def test_pass_criterion_accepts_static_mode_with_threshold(tmp_path: Path) -> None:
    issues = _validate_text(
        tmp_path,
        _rulebook_yaml(
            "      - criterion_key: quality\n"
            "        critical: true\n"
            "        artifact_kind: test_quality_gate\n"
            "        threshold_mode: static\n"
            "        threshold: 75\n"
        ),
    )
    assert issues == []


@pytest.mark.governance
def test_pass_criterion_requires_resolver_for_dynamic_mode(tmp_path: Path) -> None:
    issues = _validate_text(
        tmp_path,
        _rulebook_yaml(
            "      - criterion_key: quality\n"
            "        critical: true\n"
            "        artifact_kind: test_quality_gate\n"
            "        threshold_mode: dynamic_by_risk_tier\n"
        ),
    )
    assert any("threshold_resolver" in issue for issue in issues)


@pytest.mark.governance
def test_pass_criterion_rejects_static_mode_with_resolver(tmp_path: Path) -> None:
    issues = _validate_text(
        tmp_path,
        _rulebook_yaml(
            "      - criterion_key: quality\n"
            "        critical: true\n"
            "        artifact_kind: test_quality_gate\n"
            "        threshold_mode: static\n"
            "        threshold: 75\n"
            "        threshold_resolver: dynamic_by_risk_tier\n"
        ),
    )
    assert any("threshold_resolver" in issue for issue in issues)
