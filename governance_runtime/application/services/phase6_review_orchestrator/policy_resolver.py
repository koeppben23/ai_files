"""Policy resolver for Phase-6 review.

Resolves review mandates and effective policies from schema files and state.
This component is responsible for:
- Loading the governance mandates schema
- Extracting the review output schema
- Building human-readable mandate text
- Loading effective review policy from rulebooks

All methods are stateless and return new objects - no mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from governance_runtime.application.services.state_normalizer import normalize_to_canonical

BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE = "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"
BLOCKED_EFFECTIVE_POLICY_EMPTY = "BLOCKED-EFFECTIVE-POLICY-EMPTY"
BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID = "BLOCKED-EFFECTIVE-POLICY-SCHEMA-INVALID"
BLOCKED_RULEBOOK_CONTENT_UNLOADABLE = "BLOCKED-RULEBOOK-CONTENT-UNLOADABLE"
BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED = "BLOCKED-RULEBOOK-CONTENT-PARSE-FAILED"


@dataclass(frozen=True)
class MandateSchema:
    """Loaded mandate schema with extracted components."""

    raw_schema: dict[str, object]
    review_output_schema_text: str
    mandate_text: str


@dataclass(frozen=True)
class ReviewPolicy:
    """Effective review policy loaded from rulebooks."""

    policy_text: str
    is_available: bool
    error_code: str | None = None


class PolicyResolver:
    """Resolves review mandates and policies.

    This component encapsulates all logic for loading and formatting
    review policies and mandates. It does not depend on session state
    or LLM execution - it only deals with policy files.
    """

    def __init__(self, *, schema_path: Path | None = None) -> None:
        """Initialize the policy resolver.

        Args:
            schema_path: Path to the governance mandates schema.
                        If None, uses default location.
        """
        self._schema_path = schema_path or self._default_schema_path()

    @staticmethod
    def _default_schema_path() -> Path:
        """Get the default path to the governance mandates schema."""
        return (
            Path(__file__).parent.parent.parent.parent
            / "governance_runtime"
            / "assets"
            / "schemas"
            / "governance_mandates.v1.schema.json"
        )

    def load_mandate_schema(self) -> MandateSchema | None:
        """Load the governance mandates schema.

        Returns:
            MandateSchema if successful, None if schema file not found.
        """
        if not self._schema_path.exists():
            return None

        try:
            raw_schema = json.loads(self._schema_path.read_text(encoding="utf-8"))
        except Exception:
            return None

        review_output_schema_text = self._extract_review_output_schema(raw_schema)
        mandate_text = self._build_mandate_text(raw_schema)

        return MandateSchema(
            raw_schema=raw_schema,
            review_output_schema_text=review_output_schema_text,
            mandate_text=mandate_text,
        )

    def _extract_review_output_schema(self, schema: dict[str, object]) -> str:
        """Extract the reviewOutputSchema JSON text from the mandates schema."""
        """Extract the reviewOutputSchema JSON text from the mandates schema."""
        try:
            defs = schema.get("$defs", {})
            for key in defs:
                if key == "reviewOutputSchema":
                    return json.dumps(
                        {"$schema": "https://json-schema.org/draft/2020-12/schema", **defs[key]},
                        indent=2,
                    )
        except Exception:
            pass
        return ""

    def _build_mandate_text(self, schema: dict[str, object]) -> str:
        """Build a human-readable review mandate text from the schema."""
        rm = schema.get("review_mandate", {})
        if not isinstance(rm, dict):
            return ""

        lines: list[str] = []

        role = str(rm.get("role", "")).strip()
        if role:
            lines.append(f"Role: {role}")

        posture = rm.get("core_posture", [])
        if posture:
            for item in posture:
                lines.append(f"- {item}")

        evidence = rm.get("evidence_rule", [])
        if evidence:
            lines.append("Evidence rule:")
            for item in evidence:
                lines.append(f"- {item}")

        lenses = rm.get("review_lenses", [])
        if lenses:
            lines.append("Review lenses:")
            for idx, lens in enumerate(lenses, 1):
                if isinstance(lens, dict):
                    name = lens.get("name", "")
                    body = lens.get("body", [])
                    ask = lens.get("ask", [])
                    lines.append(f"{idx}. {name}")
                    for b in body:
                        lines.append(f"- {b}")
                    for a in ask:
                        lines.append(f"  Ask: {a}")

        method = rm.get("adversarial_method", [])
        if method:
            lines.append("Adversarial method:")
            for item in method:
                lines.append(f"- {item}")

        decision = rm.get("decision_rules", [])
        if decision:
            lines.append("Decision rules:")
            for item in decision:
                lines.append(f"- {item}")

        addendum = rm.get("governance_addendum", [])
        if addendum:
            lines.append("Governance addendum:")
            for item in addendum:
                lines.append(f"- {item}")

        return "\n".join(lines)

    def load_effective_review_policy(
        self,
        *,
        state: Mapping[str, object],
        commands_home: Path,
        clock: Callable[[], str],
        schema_path_resolver: Callable[[Path], Path],
    ) -> ReviewPolicy:
        """Load and format effective review policy for Phase 6 LLM injection.

        Args:
            state: The session state (or SESSION_STATE nested dict).
            commands_home: Path to the commands directory.
            clock: Injectable clock function that returns ISO timestamp.
            schema_path_resolver: Injectable path resolver for schema path.

        Returns:
            ReviewPolicy with policy text or error code.
        """
        from governance_runtime.application.use_cases.build_effective_llm_policy import (
            BLOCKED_EFFECTIVE_POLICY_EMPTY,
            BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID,
            BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED,
            BLOCKED_RULEBOOK_CONTENT_UNLOADABLE,
            EffectivePolicyInput,
            build_effective_llm_policy,
            format_review_policy_for_llm,
        )

        state_dict: dict[str, Any] = dict(state)
        nested = state_dict.get("SESSION_STATE")
        if isinstance(nested, dict):
            state_dict = nested

        canonical = normalize_to_canonical(state_dict)

        lrb: dict[str, object] = {}
        addons_ev: dict[str, object] = {}
        active_profile = "profile.fallback-minimum"

        loaded_rulebooks = canonical.get("loaded_rulebooks")
        if isinstance(loaded_rulebooks, dict):
            lrb = loaded_rulebooks
        addons_evidence = canonical.get("addons_evidence")
        if isinstance(addons_evidence, dict):
            addons_ev = addons_evidence
        profile_val = canonical.get("active_profile")
        if profile_val:
            active_profile = str(profile_val).strip() or "profile.fallback-minimum"

        if not lrb:
            return ReviewPolicy(
                policy_text="",
                is_available=False,
                error_code=BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            )

        base_path = Path(__file__).parent.parent.parent.parent
        base_path = schema_path_resolver(base_path)

        schema_path = (
            base_path
            / "governance_runtime"
            / "assets"
            / "schemas"
            / "effective_llm_policy.v1.schema.json"
        )

        compiled_at = clock()

        try:
            input_data = EffectivePolicyInput(
                active_profile=active_profile,
                loaded_rulebooks=lrb,
                addons_evidence=addons_ev,
                commands_home=commands_home,
                schema_path=schema_path,
                compiled_at=compiled_at,
            )
            result = build_effective_llm_policy(input_data)
            policy_text = format_review_policy_for_llm(result.policy.review_policy)
            return ReviewPolicy(policy_text=policy_text, is_available=True)
        except (
            BLOCKED_RULEBOOK_CONTENT_UNLOADABLE,
            BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED,
            BLOCKED_EFFECTIVE_POLICY_EMPTY,
            BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID,
        ):
            return ReviewPolicy(
                policy_text="",
                is_available=False,
                error_code=BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            )
        except Exception:
            return ReviewPolicy(
                policy_text="",
                is_available=False,
                error_code=BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            )
