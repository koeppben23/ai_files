from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "governance_runtime" / "docs" / "BINDING_EVIDENCE_NAMING.md"


def test_binding_evidence_doc_contains_resolution_vs_invoke_contract() -> None:
    content = DOC.read_text(encoding="utf-8")
    assert "binding_resolved=true" in content
    assert "invoke_backend_available=true" in content
    assert "binding_resolved=false`, `invoke_backend_available=false" in content
    assert "binding_resolved=true`, `invoke_backend_available=false" in content
    assert "binding_resolved=false`, `invoke_backend_available=true" in content


def test_binding_evidence_doc_contains_workspace_authority_contract() -> None:
    content = DOC.read_text(encoding="utf-8")
    assert "active workspace root" in content
    assert "resolve_active_session_paths" in content
    assert "must not derive binding mode from current working directory" in content
    assert "configured `workspace_root`" in content
