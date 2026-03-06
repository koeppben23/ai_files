from __future__ import annotations

from governance.engine.sanitization import (
    apply_fresh_start_business_rules_neutralization,
    sanitize_for_output,
)


def test_sanitize_for_output_redacts_url_credentials():
    payload = {"url": "https://user:secret-token@example.com/private"}
    sanitized = sanitize_for_output(payload)
    assert sanitized["url"] == "https://user:***@example.com/private"


def test_sanitize_for_output_redacts_secret_keys():
    payload = {"apiKey": "abc", "nested": {"password": "p", "ok": "value"}}
    sanitized = sanitize_for_output(payload)
    assert sanitized["apiKey"] == "***"
    assert sanitized["nested"]["password"] == "***"
    assert sanitized["nested"]["ok"] == "value"


def test_apply_fresh_start_business_rules_neutralization_removes_references_and_sets_neutral_values():
    state = {
        "Scope": {"BusinessRules": "extracted"},
        "BusinessRules": {
            "Decision": "execute",
            "Outcome": "extracted",
            "ExecutionEvidence": True,
            "InventoryFileStatus": "written",
            "Rules": ["BR-1: old"],
            "Evidence": ["docs/old.md:4"],
            "Inventory": {"sha256": "abc"},
        },
    }

    apply_fresh_start_business_rules_neutralization(state)

    assert state["Scope"]["BusinessRules"] == "unresolved"
    assert state["BusinessRules"]["Decision"] == "pending"
    assert state["BusinessRules"]["Outcome"] == "unresolved"
    assert state["BusinessRules"]["ExecutionEvidence"] is False
    assert state["BusinessRules"]["InventoryFileStatus"] == "unknown"
    assert "Rules" not in state["BusinessRules"]
    assert "Evidence" not in state["BusinessRules"]
    assert state["BusinessRules"]["Inventory"]["sha256"] == "0" * 64
    assert state["BusinessRules"]["Inventory"]["count"] == 0
