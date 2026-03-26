"""Build Effective LLM Policy Use Case.

LOAD  -> Load raw content from rulebook files (from LoadedRulebooks paths)
RESOLVE -> Parse content, apply precedence (core -> master -> profile -> addons)
PROJECT -> Build authoring and review policies for LLM injection

Fail-closed: any load/parse/resolve failure blocks the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from governance_runtime.application.policy.effective_policy_compiler import (
    AuthoringPolicy,
    EffectiveLLMPolicy,
    ReviewPolicy,
    compute_policy_digest,
    parse_rulebook_content,
    resolve_authoring_policy,
    resolve_review_policy,
    to_serializable,
)


class EffectivePolicyError(Exception):
    pass


class BLOCKED_RULEBOOK_CONTENT_UNLOADABLE(EffectivePolicyError):
    pass


class BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED(EffectivePolicyError):
    pass


class BLOCKED_EFFECTIVE_POLICY_EMPTY(EffectivePolicyError):
    pass


class BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID(EffectivePolicyError):
    pass


@dataclass(frozen=True)
class EffectivePolicyInput:
    active_profile: str
    loaded_rulebooks: dict[str, Any]
    addons_evidence: dict[str, Any]
    commands_home: Path
    schema_path: Path
    compiled_at: str = ""


@dataclass(frozen=True)
class EffectivePolicyOutput:
    policy: EffectiveLLMPolicy
    serializable: dict[str, Any]
    errors: tuple[str, ...] = field(default_factory=tuple)


_SCHEMA_CACHE: dict[Path, dict[str, Any]] = {}


def _load_schema(schema_path: Path) -> dict[str, Any]:
    if schema_path not in _SCHEMA_CACHE:
        if not schema_path.exists():
            msg = f"effective_llm_policy schema not found at {schema_path}"
            raise BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID(msg)
        _SCHEMA_CACHE[schema_path] = json.loads(schema_path.read_text(encoding="utf-8"))
    return _SCHEMA_CACHE[schema_path]


def _find_local_root(config_root: Path) -> Path:
    home = Path.home()
    local_root_candidate = home / ".local" / "share" / config_root.name
    if local_root_candidate.exists():
        return local_root_candidate
    local_root_legacy = config_root.parent / f"{config_root.name}-local"
    if local_root_legacy.exists():
        return local_root_legacy
    return local_root_candidate


def _resolve_content_path(
    commands_home: Path,
    path_ref: str,
    source_kind: str,
) -> Path | None:
    if not path_ref or not isinstance(path_ref, str):
        return None
    if path_ref.startswith("${COMMANDS_HOME}"):
        resolved = path_ref.replace("${COMMANDS_HOME}", str(commands_home))
        p = Path(resolved)
        return p if p.exists() else None
    if path_ref.startswith("${PROFILES_HOME}"):
        config_root = commands_home.parent
        local_root = _find_local_root(config_root)
        profiles_home = local_root / "governance_content" / "profiles"
        resolved = path_ref.replace("${PROFILES_HOME}", str(profiles_home))
        p = Path(resolved)
        return p if p.exists() else None
    if path_ref.startswith("${CONTENT_HOME}"):
        config_root = commands_home.parent
        local_root = _find_local_root(config_root)
        content_home = local_root / "governance_content"
        resolved = path_ref.replace("${CONTENT_HOME}", str(content_home))
        p = Path(resolved)
        if p.exists():
            return p
        fallback = config_root / path_ref.replace("${CONTENT_HOME}/", "")
        return fallback if fallback.exists() else None
    if path_ref.startswith("${SPEC_HOME}"):
        config_root = commands_home.parent
        local_root = _find_local_root(config_root)
        spec_home = local_root / "governance_spec"
        resolved = path_ref.replace("${SPEC_HOME}", str(spec_home))
        p = Path(resolved)
        return p if p.exists() else None
    if path_ref.startswith("${CONFIG_ROOT}"):
        config_root = commands_home.parent
        resolved = path_ref.replace("${CONFIG_ROOT}", str(config_root))
        p = Path(resolved)
        return p if p.exists() else None
    p = Path(path_ref)
    if p.is_absolute() and p.exists():
        return p
    candidates = [
        commands_home / path_ref,
        commands_home.parent / path_ref,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def build_effective_llm_policy(input: EffectivePolicyInput) -> EffectivePolicyOutput:
    """Build effective LLM policy from loaded rulebooks and addons.

    Load
      -> Load raw content from paths in LoadedRulebooks
    Resolve
      -> Parse markdown, apply precedence
    Project
      -> Build AuthoringPolicy + ReviewPolicy
    Validate
      -> Against effective_llm_policy.v1.schema.json
    Fail-closed on any error.
    """
    errors: list[str] = []
    commands_home = input.commands_home
    schema_path = input.schema_path
    effective_schema_path = schema_path

    source_refs: dict[str, dict[str, str]] = {}
    parsed_contents: list[tuple[str, str, Any]] = []

    def _load_content(identifier: str, path_ref: str, source_kind: str) -> Any:
        if not path_ref or path_ref in ("", "not-loaded"):
            errors.append(f"rulebook path empty for {identifier} ({source_kind})")
            return None
        content_path = _resolve_content_path(commands_home, path_ref, source_kind)
        if content_path is None:
            errors.append(
                f"rulebook content not loadable: {identifier} at {path_ref}"
            )
            raise BLOCKED_RULEBOOK_CONTENT_UNLOADABLE(
                f"Cannot load rulebook {identifier} from {path_ref}"
            )
        try:
            raw_text = content_path.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"read failed for {identifier}: {exc}")
            raise BLOCKED_RULEBOOK_CONTENT_UNLOADABLE(
                f"Cannot read rulebook {identifier} from {content_path}: {exc}"
            ) from exc

        if not raw_text.strip():
            errors.append(f"rulebook content empty for {identifier}")
            raise BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED(
                f"Rulebook {identifier} has no content"
            )

        try:
            parsed = parse_rulebook_content(identifier, source_kind, str(content_path), raw_text)
        except Exception as exc:
            errors.append(f"parse failed for {identifier}: {exc}")
            raise BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED(
                f"Cannot parse rulebook {identifier}: {exc}"
            ) from exc

        source_refs[identifier] = {
            "path": str(content_path),
            "sha256": parsed.sha256,
            "source_kind": source_kind,
        }
        return parsed

    core_rb: Any = None
    master_rb: Any = None
    profile_rb: Any = None
    addon_rbs: list[Any] = []

    lrb = input.loaded_rulebooks
    if isinstance(lrb, dict):
        core_path = lrb.get("core", "") or ""
        master_path = lrb.get("master", "") or lrb.get("templates", "") or ""
        profile_path = lrb.get("profile", "") or ""
        addons_map = lrb.get("addons", {}) or {}

        if core_path:
            try:
                core_rb = _load_content("core", core_path, "core")
            except EffectivePolicyError:
                core_rb = None

        if master_path:
            try:
                master_rb = _load_content("master", master_path, "master")
            except EffectivePolicyError:
                master_rb = None

        if profile_path:
            try:
                profile_rb = _load_content(
                    input.active_profile,
                    profile_path,
                    "profile",
                )
            except EffectivePolicyError:
                profile_rb = None

        if isinstance(addons_map, dict):
            for addon_key, addon_path in addons_map.items():
                if addon_key and addon_path and addon_key not in ("templates",):
                    try:
                        addon_rb = _load_content(addon_key, addon_path, "addon")
                        if addon_rb:
                            addon_rbs.append(addon_rb)
                    except EffectivePolicyError:
                        pass

    authoring_policy = resolve_authoring_policy(
        core=core_rb,
        master=master_rb,
        profile=profile_rb,
        addons=tuple(addon_rbs),
    )
    review_policy = resolve_review_policy(
        core=core_rb,
        master=master_rb,
        profile=profile_rb,
        addons=tuple(addon_rbs),
    )

    policy = EffectiveLLMPolicy(
        schema_version="1.0.0",
        compiled_at=input.compiled_at,
        source_digest="",
        evidence={
            "active_profile": input.active_profile,
            "active_addons": [
                k for k in (input.addons_evidence or {}).keys() if k
            ],
            "source_refs": source_refs,
        },
        authoring_policy=authoring_policy,
        review_policy=review_policy,
    )

    policy_digest = compute_policy_digest(policy)
    object.__setattr__(policy, "source_digest", policy_digest)

    serializable = to_serializable(policy)

    if effective_schema_path.exists():
        try:
            schema = _load_schema(effective_schema_path)
            validator = Draft7Validator(schema)
            errors_out = list(validator.iter_errors(serializable))
            if errors_out:
                err_msgs = [f"{e.json_path}: {e.message}" for e in errors_out]
                errors.extend(err_msgs)
                raise BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID(
                    f"Policy schema validation failed: {err_msgs[0]}"
                )
        except BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID:
            raise
        except Exception as exc:
            errors.append(f"schema validation error: {exc}")

    authoring_has_content = bool(
        authoring_policy.profile_constraints
        or authoring_policy.addon_constraints
        or authoring_policy.required_checks
        or authoring_policy.quality_priorities
    )
    review_has_content = bool(
        review_policy.profile_constraints
        or review_policy.addon_constraints
        or review_policy.required_checks
    )

    if not authoring_has_content and not review_has_content:
        errors.append("effective policy is empty: no authoring or review constraints")
        raise BLOCKED_EFFECTIVE_POLICY_EMPTY(
            "Resulting policy has no effective constraints"
        )

    return EffectivePolicyOutput(
        policy=policy,
        serializable=serializable,
        errors=tuple(errors),
    )


def format_authoring_policy_for_llm(policy: AuthoringPolicy) -> str:
    """Format authoring policy as readable text for LLM injection."""
    lines: list[str] = ["[EFFECTIVE AUTHORING POLICY]"]
    if policy.profile_constraints:
        lines.append("Profile constraints:")
        for item in policy.profile_constraints:
            lines.append(f"  - {item}")
    if policy.addon_constraints:
        lines.append("Addon constraints:")
        for item in policy.addon_constraints:
            lines.append(f"  - {item}")
    if policy.quality_priorities:
        lines.append("Quality priorities:")
        for item in policy.quality_priorities:
            lines.append(f"  - {item}")
    if policy.forbidden_behaviors:
        lines.append("Forbidden behaviors:")
        for item in policy.forbidden_behaviors:
            lines.append(f"  - {item}")
    if policy.required_checks:
        lines.append("Required checks:")
        for item in policy.required_checks:
            lines.append(f"  - {item}")
    if policy.naming_conventions:
        lines.append("Naming conventions:")
        for item in policy.naming_conventions:
            lines.append(f"  - {item}")
    if policy.tooling_commands:
        lines.append("Tooling:")
        for item in policy.tooling_commands:
            lines.append(f"  - {item}")
    if policy.profile_anti_patterns:
        lines.append("Anti-patterns:")
        for item in policy.profile_anti_patterns:
            lines.append(f"  - {item}")
    if policy.definition_of_done:
        lines.append("Definition of done:")
        for item in policy.definition_of_done:
            lines.append(f"  - {item}")
    if policy.governance_addendum:
        lines.append("Governance:")
        for item in policy.governance_addendum:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def format_review_policy_for_llm(policy: ReviewPolicy) -> str:
    """Format review policy as readable text for LLM injection."""
    lines: list[str] = ["[EFFECTIVE REVIEW POLICY]"]
    if policy.profile_constraints:
        lines.append("Profile review constraints:")
        for item in policy.profile_constraints:
            lines.append(f"  - {item}")
    if policy.addon_constraints:
        lines.append("Addon review constraints:")
        for item in policy.addon_constraints:
            lines.append(f"  - {item}")
    if policy.required_lenses:
        lines.append("Required review lenses:")
        for item in policy.required_lenses:
            name = item.get("name", "?")
            focus = item.get("focus", "")
            lines.append(f"  - {name}: {focus}")
    if policy.tier_evidence_minimums:
        lines.append("Tier evidence minimums:")
        for tier, items in policy.tier_evidence_minimums.items():
            lines.append(f"  {tier}:")
            for item in items:
                lines.append(f"    - {item}")
    if policy.required_checks:
        lines.append("Required review checks:")
        for item in policy.required_checks:
            lines.append(f"  - {item}")
    if policy.forbidden_behaviors:
        lines.append("Forbidden review behaviors:")
        for item in policy.forbidden_behaviors:
            lines.append(f"  - {item}")
    if policy.governance_addendum:
        lines.append("Governance:")
        for item in policy.governance_addendum:
            lines.append(f"  - {item}")
    return "\n".join(lines)
