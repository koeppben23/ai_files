from __future__ import annotations

from governance.engine.canonical_json import (
    canonical_json_bytes,
    canonical_json_clone,
    canonical_json_hash,
    canonical_json_text,
)


def test_canonical_json_text_is_order_stable():
    a = {"b": 2, "a": {"y": 2, "x": 1}}
    b = {"a": {"x": 1, "y": 2}, "b": 2}
    assert canonical_json_text(a) == canonical_json_text(b)


def test_canonical_json_hash_is_order_stable():
    a = {"z": [3, 2, 1], "a": "x"}
    b = {"a": "x", "z": [3, 2, 1]}
    assert canonical_json_hash(a) == canonical_json_hash(b)


def test_canonical_json_bytes_are_lf_normalized():
    payload = {"line": "one\r\ntwo\rthree\nfour"}
    data = canonical_json_bytes(payload)
    assert b"\r" not in data
    assert b"one\\ntwo\\nthree\\nfour" in data


def test_canonical_json_clone_is_deep_copy():
    payload = {"outer": {"inner": [1, 2, 3]}}
    cloned = canonical_json_clone(payload)
    assert cloned == payload
    assert cloned is not payload
    assert cloned["outer"] is not payload["outer"]
