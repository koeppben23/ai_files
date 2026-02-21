"""Engine selfcheck for deterministic governance invariants."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from pathlib import Path
from typing import Iterable

from diagnostics.reason_registry_selfcheck import check_reason_registry_parity
from governance.domain.reason_codes import BLOCKED_ENGINE_SELFCHECK, CANONICAL_REASON_CODES, is_registered_reason_code
from governance.engine.mode_repo_rules import canonicalize_operating_mode
from governance.infrastructure.policy_bundle_loader import ensure_policy_bundle_loaded


@dataclass(frozen=True)
class EngineSelfcheckResult:
    ok: bool
    failed_checks: tuple[str, ...]


_RELEASE_METADATA_BLOCKLIST = (
    "__MACOSX",
    ".DS_Store",
)


def _effective_mode() -> str:
    token = str(os.environ.get("OPENCODE_OPERATING_MODE", "")).strip()
    if token:
        return canonicalize_operating_mode(token)
    ci = str(os.environ.get("CI", "")).strip().lower()
    if ci and ci not in {"0", "false", "no", "off"}:
        return "pipeline"
    return "user"


def _find_duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for value in values:
        if value in seen:
            dupes.add(value)
        else:
            seen.add(value)
    return dupes


def _check_reason_registry_duplicates() -> tuple[bool, str | None]:
    duplicates = _find_duplicates(CANONICAL_REASON_CODES)
    if duplicates:
        return False, "reason_code_registry_has_duplicates"
    return True, None


def _check_blocked_engine_selfcheck_registered() -> tuple[bool, str | None]:
    if not is_registered_reason_code(BLOCKED_ENGINE_SELFCHECK, allow_none=False):
        return False, "blocked_engine_selfcheck_missing"
    return True, None


def _check_reason_registry_parity(repo_root: Path) -> tuple[bool, str | None]:
    ok, _errors = check_reason_registry_parity(repo_root=repo_root)
    if not ok:
        return False, "reason_registry_parity_failed"
    return True, None


def _check_yaml_reason_refs(repo_root: Path) -> tuple[bool, str | None]:
    yaml_root = repo_root / "diagnostics"
    unknown: set[str] = set()
    if yaml_root.exists():
        for yaml_path in sorted(yaml_root.glob("*.yaml")):
            try:
                text = yaml_path.read_text(encoding="utf-8")
            except Exception:
                continue
            for code in re.findall(r"BLOCKED-[A-Z0-9-]+", text):
                if not is_registered_reason_code(code, allow_none=False):
                    unknown.add(code)
    if unknown:
        return False, "reason_registry_yaml_refs_unregistered"
    return True, None


def _check_policy_bundle_selfcheck(mode: str) -> tuple[bool, str | None]:
    if mode == "invalid":
        return False, "operating_mode_invalid"
    try:
        ensure_policy_bundle_loaded(mode=mode)
    except Exception:
        return False, "policy_bundle_load_failed"
    return True, None


def _check_release_metadata_hygiene(entries: Iterable[str]) -> tuple[bool, str | None]:
    for entry in entries:
        token = str(entry)
        for blocked in _RELEASE_METADATA_BLOCKLIST:
            if blocked in token:
                return False, "release_metadata_hygiene_violation"
    return True, None


def run_engine_selfcheck(*, release_hygiene_entries: tuple[str, ...] = ()) -> EngineSelfcheckResult:
    failed: list[str] = []
    repo_root = Path(__file__).absolute().parents[2]
    effective_mode = _effective_mode()

    checks = (
        _check_reason_registry_duplicates(),
        _check_blocked_engine_selfcheck_registered(),
        _check_reason_registry_parity(repo_root),
        _check_yaml_reason_refs(repo_root),
        _check_policy_bundle_selfcheck(effective_mode),
        _check_release_metadata_hygiene(release_hygiene_entries),
    )

    for ok, failure in checks:
        if not ok and failure:
            failed.append(failure)

    failed_sorted = tuple(sorted(set(failed)))
    return EngineSelfcheckResult(ok=not failed_sorted, failed_checks=failed_sorted)
