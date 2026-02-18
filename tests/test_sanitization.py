from __future__ import annotations

from governance.engine.sanitization import sanitize_for_output


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
