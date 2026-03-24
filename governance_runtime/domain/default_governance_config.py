"""Default governance configuration values.

This module provides the default values for governance configuration.
These defaults match the current hardcoded behavior to ensure
backward compatibility when governance-config.json is introduced.

Defaults are intentionally conservative and match existing behavior:
- review iterations: 3
- pipeline mode: allowed
- pipeline auto-approve: enabled
- regulated auto-approve: disabled (should always be false)
- require governance-mode active: true
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ReviewDefaults:
    phase5_max_review_iterations: int = 3
    phase6_max_review_iterations: int = 3


@dataclass(frozen=True)
class PipelineDefaults:
    allow_pipeline_mode: bool = True
    auto_approve_enabled: bool = True


@dataclass(frozen=True)
class RegulatedDefaults:
    allow_auto_approve: bool = False
    require_governance_mode_active: bool = True


@dataclass(frozen=True)
class GovernanceConfigDefaults:
    review: ReviewDefaults = ReviewDefaults()
    pipeline: PipelineDefaults = PipelineDefaults()
    regulated: RegulatedDefaults = RegulatedDefaults()


DEFAULT_REVIEW = ReviewDefaults()
DEFAULT_PIPELINE = PipelineDefaults()
DEFAULT_REGULATED = RegulatedDefaults()
DEFAULT_GOVERNANCE_CONFIG = GovernanceConfigDefaults()

SCHEMA_VERSION = "governance-config.v1.schema.json"


def get_default_review_config() -> dict:
    return {
        "phase5_max_review_iterations": DEFAULT_REVIEW.phase5_max_review_iterations,
        "phase6_max_review_iterations": DEFAULT_REVIEW.phase6_max_review_iterations,
    }


def get_default_pipeline_config() -> dict:
    return {
        "allow_pipeline_mode": DEFAULT_PIPELINE.allow_pipeline_mode,
        "auto_approve_enabled": DEFAULT_PIPELINE.auto_approve_enabled,
    }


def get_default_regulated_config() -> dict:
    return {
        "allow_auto_approve": DEFAULT_REGULATED.allow_auto_approve,
        "require_governance_mode_active": DEFAULT_REGULATED.require_governance_mode_active,
    }


def get_default_governance_config() -> dict:
    return {
        "$schema": SCHEMA_VERSION,
        "review": get_default_review_config(),
        "pipeline": get_default_pipeline_config(),
        "regulated": get_default_regulated_config(),
    }


__all__ = [
    "ReviewDefaults",
    "PipelineDefaults",
    "RegulatedDefaults",
    "GovernanceConfigDefaults",
    "DEFAULT_REVIEW",
    "DEFAULT_PIPELINE",
    "DEFAULT_REGULATED",
    "DEFAULT_GOVERNANCE_CONFIG",
    "SCHEMA_VERSION",
    "get_default_review_config",
    "get_default_pipeline_config",
    "get_default_regulated_config",
    "get_default_governance_config",
]
