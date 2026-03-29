"""Default governance configuration values.

This module provides default values for governance configuration and
preserves backward compatibility when governance-config.json is missing.

Current defaults include:
- pipeline_mode: false (direct mode default)
- presentation.mode: standard (compact Session-State readout)
- review.phase5_max_review_iterations: 3
- review.phase6_max_review_iterations: 3
"""

from __future__ import annotations

from dataclasses import dataclass


SCHEMA_ID = "governance-config.v1.schema.json"


@dataclass(frozen=True)
class PresentationDefaults:
    mode: str = "standard"


DEFAULT_PRESENTATION = PresentationDefaults()


@dataclass(frozen=True)
class ReviewDefaults:
    phase5_max_review_iterations: int = 3
    phase6_max_review_iterations: int = 3


DEFAULT_REVIEW = ReviewDefaults()


def get_default_presentation_config() -> dict:
    return {
        "mode": DEFAULT_PRESENTATION.mode,
    }


def get_default_review_config() -> dict:
    return {
        "phase5_max_review_iterations": DEFAULT_REVIEW.phase5_max_review_iterations,
        "phase6_max_review_iterations": DEFAULT_REVIEW.phase6_max_review_iterations,
    }


def get_default_governance_config() -> dict:
    return {
        "pipeline_mode": False,
        "presentation": get_default_presentation_config(),
        "review": get_default_review_config(),
    }


__all__ = [
    "PresentationDefaults",
    "DEFAULT_PRESENTATION",
    "ReviewDefaults",
    "DEFAULT_REVIEW",
    "SCHEMA_ID",
    "get_default_presentation_config",
    "get_default_review_config",
    "get_default_governance_config",
]
