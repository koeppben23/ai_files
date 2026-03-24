"""Default governance configuration values.

This module provides the default values for governance configuration.
These defaults match the current hardcoded behavior to ensure
backward compatibility when governance-config.json is introduced.

V1 only includes review iteration knobs:
- phase5_max_review_iterations: 3
- phase6_max_review_iterations: 3

Other governance settings (pipeline, regulated) are controlled elsewhere
and are not part of V1 governance-config.json.
"""

from __future__ import annotations

from dataclasses import dataclass


SCHEMA_ID = "governance-config.v1.schema.json"


@dataclass(frozen=True)
class ReviewDefaults:
    phase5_max_review_iterations: int = 3
    phase6_max_review_iterations: int = 3


DEFAULT_REVIEW = ReviewDefaults()


def get_default_review_config() -> dict:
    return {
        "phase5_max_review_iterations": DEFAULT_REVIEW.phase5_max_review_iterations,
        "phase6_max_review_iterations": DEFAULT_REVIEW.phase6_max_review_iterations,
    }


def get_default_governance_config() -> dict:
    return {
        "review": get_default_review_config(),
    }


__all__ = [
    "ReviewDefaults",
    "DEFAULT_REVIEW",
    "SCHEMA_ID",
    "get_default_review_config",
    "get_default_governance_config",
]
