"""Validation helpers for requirement contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

_REQUIRED_FIELDS = (
    "id",
    "title",
    "criticality",
    "owner_test",
    "live_proof_key",
    "required_behavior",
    "forbidden_behavior",
    "user_visible_expectation",
    "state_expectation",
    "code_hotspots",
    "verification_methods",
    "acceptance_tests",
    "done_rule",
)

_ALLOWED_CRITICALITY = {"release_blocking", "important", "normal"}
_ALLOWED_VERIFICATION_METHODS = {
    "static_verification",
    "behavioral_verification",
    "user_surface_verification",
    "live_flow_verification",
    "receipts_verification",
}


@dataclass(frozen=True)
class ContractValidationResult:
    ok: bool
    errors: tuple[str, ...]


def _is_non_empty_list_of_strings(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return False
    return True


def _as_text(value: object) -> str:
    return str(value or "").strip()


def validate_requirement_contract(contract: Mapping[str, object]) -> list[str]:
    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        if field not in contract:
            errors.append(f"missing_required_field:{field}")

    if errors:
        return errors

    criticality = _as_text(contract.get("criticality"))
    if criticality not in _ALLOWED_CRITICALITY:
        errors.append("invalid_criticality")

    for field in ("id", "title", "owner_test", "live_proof_key"):
        if not _as_text(contract.get(field)):
            errors.append(f"empty_text_field:{field}")

    for field in (
        "required_behavior",
        "forbidden_behavior",
        "user_visible_expectation",
        "state_expectation",
        "code_hotspots",
        "acceptance_tests",
    ):
        if not _is_non_empty_list_of_strings(contract.get(field)):
            errors.append(f"invalid_non_empty_string_list:{field}")

    verification_methods = contract.get("verification_methods")
    if not _is_non_empty_list_of_strings(verification_methods):
        errors.append("invalid_non_empty_string_list:verification_methods")
    else:
        verified_methods = verification_methods if isinstance(verification_methods, list) else []
        methods = {str(item).strip() for item in verified_methods if str(item).strip()}
        if not methods.issubset(_ALLOWED_VERIFICATION_METHODS):
            errors.append("invalid_verification_methods")
        if _as_text(contract.get("criticality")) == "release_blocking" and "live_flow_verification" not in methods:
            errors.append("release_blocking_requires_live_flow_verification")
        forbidden_behavior = contract.get("forbidden_behavior")
        forbidden_items = forbidden_behavior if isinstance(forbidden_behavior, list) else []
        touches_decision = any("decision" in str(s).lower() for s in forbidden_items)
        touches_presentation = "presentation" in _as_text(contract.get("title")).lower()
        if (touches_decision or touches_presentation) and "receipts_verification" not in methods:
            errors.append("decision_or_presentation_requires_receipts_verification")

    done_rule = contract.get("done_rule")
    if not isinstance(done_rule, Mapping):
        errors.append("invalid_done_rule")
    else:
        for key in (
            "require_all_verifications_pass",
            "fail_closed_on_missing_evidence",
            "fail_on_forbidden_observation",
        ):
            if not isinstance(done_rule.get(key), bool):
                errors.append(f"invalid_done_rule_flag:{key}")

    return errors


def validate_requirement_contracts(contracts: Iterable[Mapping[str, object]]) -> ContractValidationResult:
    errors: list[str] = []
    seen_ids: dict[str, int] = {}
    seen_owner_tests: dict[str, str] = {}
    seen_live_keys: dict[str, str] = {}

    for idx, contract in enumerate(contracts, start=1):
        contract_id = _as_text(contract.get("id")) or f"<index:{idx}>"

        for err in validate_requirement_contract(contract):
            errors.append(f"{contract_id}:{err}")

        seen_ids[contract_id] = seen_ids.get(contract_id, 0) + 1

        owner_test = _as_text(contract.get("owner_test"))
        if owner_test:
            previous = seen_owner_tests.get(owner_test)
            if previous and previous != contract_id:
                errors.append(
                    f"{contract_id}:duplicate_owner_test_repo_wide:{owner_test}:already_used_by:{previous}"
                )
            else:
                seen_owner_tests[owner_test] = contract_id

        live_key = _as_text(contract.get("live_proof_key"))
        if live_key:
            previous = seen_live_keys.get(live_key)
            if previous and previous != contract_id:
                errors.append(
                    f"{contract_id}:duplicate_live_proof_key_repo_wide:{live_key}:already_used_by:{previous}"
                )
            else:
                seen_live_keys[live_key] = contract_id

    for contract_id, count in seen_ids.items():
        if count > 1:
            errors.append(f"{contract_id}:duplicate_requirement_id")

    return ContractValidationResult(ok=not errors, errors=tuple(errors))
