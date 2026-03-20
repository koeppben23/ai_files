from __future__ import annotations

from pathlib import Path

import scripts.ssot_guard as ssot_guard


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_canonical(tmp_path: Path) -> None:
    _write(tmp_path / "governance_content" / "reference" / "master.md", "master")
    _write(tmp_path / "governance_content" / "reference" / "rules.md", "rules")
    _write(tmp_path / "README.md", "readme")
    _write(tmp_path / "QUICKSTART.md", "quickstart")


def test_ssot_duplicate_guard_happy(monkeypatch, tmp_path: Path) -> None:
    _seed_canonical(tmp_path)
    monkeypatch.setattr(ssot_guard, "REPO_ROOT", tmp_path)
    issues: list[str] = []
    ssot_guard._validate_canonical_uniqueness(issues)
    ssot_guard._validate_byte_identical_duplicates(issues)
    assert issues == []


def test_ssot_duplicate_guard_bad_duplicate(monkeypatch, tmp_path: Path) -> None:
    _seed_canonical(tmp_path)
    _write(tmp_path / "governance_spec" / "master.md", "shadow")
    monkeypatch.setattr(ssot_guard, "REPO_ROOT", tmp_path)
    issues: list[str] = []
    ssot_guard._validate_canonical_uniqueness(issues)
    assert any("non-canonical normative duplicate" in item for item in issues)


def test_ssot_duplicate_guard_corner_archived_duplicate_allowed(monkeypatch, tmp_path: Path) -> None:
    _seed_canonical(tmp_path)
    _write(tmp_path / "governance_content" / "docs" / "archived" / "master.md", "archived")
    monkeypatch.setattr(ssot_guard, "REPO_ROOT", tmp_path)
    issues: list[str] = []
    ssot_guard._validate_canonical_uniqueness(issues)
    assert issues == []


def test_ssot_duplicate_guard_edge_byte_identical(monkeypatch, tmp_path: Path) -> None:
    _seed_canonical(tmp_path)
    _write(tmp_path / "governance_spec" / "rules.yml", "same-content")
    _write(tmp_path / "templates" / "rules.yml", "same-content")
    monkeypatch.setattr(ssot_guard, "REPO_ROOT", tmp_path)
    issues: list[str] = []
    ssot_guard._validate_byte_identical_duplicates(issues)
    assert any("byte-identical normative duplicates" in item for item in issues)
