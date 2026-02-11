from __future__ import annotations

import pytest

from governance.persistence.write_policy import (
    BLOCKED_PERSISTENCE_PATH_VIOLATION,
    BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
    DETAIL_KEY_PARENT_TRAVERSAL,
    DETAIL_KEY_UNKNOWN_VARIABLE,
    DETAIL_OK,
    evaluate_target_path,
)


@pytest.mark.governance
@pytest.mark.parametrize(
    "target",
    [
        "C",
        "C:",
        "C:tmp\\file",
        "rules.md",
        "business-rules.md",
        "tmp",
        "",
    ],
)
def test_write_policy_rejects_degenerate_targets(target: str):
    """Degenerate write-target forms must fail closed with the degenerate code."""

    result = evaluate_target_path(target)
    assert result.valid is False
    assert result.reason_code == BLOCKED_PERSISTENCE_TARGET_DEGENERATE


@pytest.mark.governance
@pytest.mark.parametrize(
    "target",
    [
        "workspaces/repo/SESSION_STATE.json",
        "/Users/example/.config/opencode/workspaces/abc/repo-cache.yaml",
    ],
)
def test_write_policy_rejects_non_variable_paths(target: str):
    """Non-variable paths are invalid even when they are not degenerate."""

    result = evaluate_target_path(target)
    assert result.valid is False
    assert result.reason_code == BLOCKED_PERSISTENCE_PATH_VIOLATION


@pytest.mark.governance
@pytest.mark.parametrize(
    "target",
    [
        "${REPO_CACHE_FILE}",
        "${REPO_BUSINESS_RULES_FILE}",
        "${WORKSPACES_HOME}/abc/SESSION_STATE.json",
    ],
)
def test_write_policy_accepts_canonical_variable_targets(target: str):
    """Canonical variable-based targets must pass validation."""

    result = evaluate_target_path(target)
    assert result.valid is True
    assert result.reason_code == "none"
    assert result.detail_key == DETAIL_OK


@pytest.mark.governance
@pytest.mark.parametrize(
    "target",
    [
        "${UNKNOWN_VAR}/repo-cache.yaml",
        "${WORKSPACES_HOME}/../repo-cache.yaml",
        "${WORKSPACES_HOME}/a//b/../../repo-cache.yaml",
        "${WORKSPACES_HOME/repo-cache.yaml",
    ],
)
def test_write_policy_rejects_unknown_or_traversal_variable_paths(target: str):
    """Variable paths must use allowlisted variables and forbid parent traversal."""

    result = evaluate_target_path(target)
    assert result.valid is False
    assert result.reason_code == BLOCKED_PERSISTENCE_PATH_VIOLATION


@pytest.mark.governance
def test_write_policy_exposes_stable_detail_key_for_unknown_variable():
    """Unknown variable rejections should expose deterministic detail keys."""

    result = evaluate_target_path("${UNKNOWN_VAR}/repo-cache.yaml")
    assert result.valid is False
    assert result.detail_key == DETAIL_KEY_UNKNOWN_VARIABLE


@pytest.mark.governance
def test_write_policy_exposes_stable_detail_key_for_parent_traversal():
    """Parent traversal rejections should expose deterministic detail keys."""

    result = evaluate_target_path("${WORKSPACES_HOME}/../repo-cache.yaml")
    assert result.valid is False
    assert result.detail_key == DETAIL_KEY_PARENT_TRAVERSAL
