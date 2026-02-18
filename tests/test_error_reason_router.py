from __future__ import annotations

from governance.engine.error_reason_router import canonicalize_reason_payload_failure


def test_reason_router_maps_contract_violation_bucket():
    cls, detail = canonicalize_reason_payload_failure(ValueError("invalid reason payload:foo"))
    assert (cls, detail) == ("reason_payload_invalid", "schema_or_contract_violation")


def test_reason_router_maps_registry_bucket():
    cls, detail = canonicalize_reason_payload_failure(ValueError("reason_registry_invalid:no_usable_mappings"))
    assert (cls, detail) == ("reason_registry_invalid", "registry_unavailable_or_invalid")


def test_reason_router_maps_unknown_exception_bucket():
    cls, detail = canonicalize_reason_payload_failure(RuntimeError("boom"))
    assert cls == "reason_payload_build_failed"
    assert detail == "runtimeerror"
