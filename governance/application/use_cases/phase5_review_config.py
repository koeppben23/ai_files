"""Phase 5 Review Configuration Loader.

SSOT loader for Phase 5 iterative review settings.
Config is loaded from diagnostics/phase5_review_config.yaml.

Operating Modes:
- user: Human escalation enabled
- pipeline: NO human interaction, fail-fast
- agents_strict: No auto-approve
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Any

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore
    YAML_AVAILABLE = False


OperatingMode = Literal["user", "pipeline", "agents_strict"]
PipelineFallback = Literal["reject", "approve_with_warnings"]


@dataclass(frozen=True)
class ReviewCriteria:
    """Review criteria that must pass for approval."""
    test_coverage_min_percent: int = 80
    security_scan_required: bool = True
    architecture_doc_required: bool = True
    breaking_changes_documented: bool = True
    rollback_plan_required: bool = False


@dataclass(frozen=True)
class ModeConfig:
    """Configuration for a specific operating mode."""
    human_escalation_enabled: bool = True
    auto_approve_on_no_issues: bool = True
    auto_reject_on_blocking_issues: bool = False
    max_iterations: int = 3
    fail_fast: bool = False


@dataclass(frozen=True)
class EscalationConfig:
    """Escalation policy configuration."""
    triggers: tuple[str, ...] = (
        "open_questions_after_max_iterations",
        "unresolved_issues_after_max_iterations",
        "explicit_needs_human_status",
    )
    pipeline_fallback: PipelineFallback = "reject"


@dataclass(frozen=True)
class AuditConfig:
    """Audit logging configuration."""
    log_all_feedback: bool = True
    persist_feedback_history: bool = True
    include_timestamps: bool = True
    retention_days: int = 90


@dataclass(frozen=True)
class MetricsConfig:
    """Metrics collection configuration."""
    track_review_duration: bool = True
    track_issues_per_iteration: bool = True
    track_approval_rate: bool = True


@dataclass(frozen=True)
class Phase5ReviewConfig:
    """SSOT configuration for Phase 5 iterative review."""
    max_iterations: int = 3
    criteria: ReviewCriteria = field(default_factory=ReviewCriteria)
    modes: dict[str, ModeConfig] = field(default_factory=lambda: {
        "user": ModeConfig(
            human_escalation_enabled=True,
            auto_approve_on_no_issues=True,
            max_iterations=3,
        ),
        "pipeline": ModeConfig(
            human_escalation_enabled=False,
            auto_approve_on_no_issues=True,
            auto_reject_on_blocking_issues=True,
            max_iterations=3,
            fail_fast=True,
        ),
        "agents_strict": ModeConfig(
            human_escalation_enabled=False,
            auto_approve_on_no_issues=False,
            max_iterations=1,
        ),
    })
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Phase5ReviewConfig":
        """Create config from dictionary (parsed YAML)."""
        criteria_data = data.get("criteria", {})
        criteria = ReviewCriteria(
            test_coverage_min_percent=criteria_data.get("test_coverage_min_percent", 80),
            security_scan_required=criteria_data.get("security_scan_required", True),
            architecture_doc_required=criteria_data.get("architecture_doc_required", True),
            breaking_changes_documented=criteria_data.get("breaking_changes_documented", True),
            rollback_plan_required=criteria_data.get("rollback_plan_required", False),
        )
        
        modes_data = data.get("modes", {})
        modes: dict[str, ModeConfig] = {}
        for mode_name, mode_cfg in modes_data.items():
            modes[mode_name] = ModeConfig(
                human_escalation_enabled=mode_cfg.get("human_escalation_enabled", True),
                auto_approve_on_no_issues=mode_cfg.get("auto_approve_on_no_issues", True),
                auto_reject_on_blocking_issues=mode_cfg.get("auto_reject_on_blocking_issues", False),
                max_iterations=mode_cfg.get("max_iterations", 3),
                fail_fast=mode_cfg.get("fail_fast", False),
            )
        
        escalation_data = data.get("escalation", {})
        escalation = EscalationConfig(
            triggers=tuple(escalation_data.get("triggers", [])),
            pipeline_fallback=escalation_data.get("pipeline_fallback", "reject"),
        )
        
        audit_data = data.get("audit", {})
        audit = AuditConfig(
            log_all_feedback=audit_data.get("log_all_feedback", True),
            persist_feedback_history=audit_data.get("persist_feedback_history", True),
            include_timestamps=audit_data.get("include_timestamps", True),
            retention_days=audit_data.get("retention_days", 90),
        )
        
        metrics_data = data.get("metrics", {})
        metrics = MetricsConfig(
            track_review_duration=metrics_data.get("track_review_duration", True),
            track_issues_per_iteration=metrics_data.get("track_issues_per_iteration", True),
            track_approval_rate=metrics_data.get("track_approval_rate", True),
        )
        
        return cls(
            max_iterations=data.get("max_iterations", 3),
            criteria=criteria,
            modes=modes,
            escalation=escalation,
            audit=audit,
            metrics=metrics,
        )
    
    def get_mode_config(self, mode: OperatingMode) -> ModeConfig:
        """Get configuration for a specific operating mode."""
        return self.modes.get(mode, self.modes["user"])


_CONFIG_CACHE: Phase5ReviewConfig | None = None


def load_phase5_review_config(*, force_reload: bool = False) -> Phase5ReviewConfig:
    """Load Phase 5 review config from YAML file (SSOT).
    
    Config is cached after first load. Use force_reload=True to reload.
    Falls back to defaults if YAML is not available.
    """
    global _CONFIG_CACHE
    
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE
    
    config_path = Path(__file__).parent.parent.parent.parent / "diagnostics" / "phase5_review_config.yaml"
    
    if config_path.exists() and YAML_AVAILABLE:
        import yaml as yaml_loader  # type: ignore
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml_loader.safe_load(f) or {}
        _CONFIG_CACHE = Phase5ReviewConfig.from_dict(data)
    else:
        _CONFIG_CACHE = Phase5ReviewConfig()
    
    return _CONFIG_CACHE
    
    config_path = Path(__file__).parent.parent / "diagnostics" / "phase5_review_config.yaml"
    
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _CONFIG_CACHE = Phase5ReviewConfig.from_dict(data)
    else:
        _CONFIG_CACHE = Phase5ReviewConfig()
    
    return _CONFIG_CACHE


def get_max_iterations(mode: OperatingMode) -> int:
    """Get max iterations for operating mode."""
    config = load_phase5_review_config()
    return config.get_mode_config(mode).max_iterations


def is_human_escalation_enabled(mode: OperatingMode) -> bool:
    """Check if human escalation is enabled for operating mode."""
    config = load_phase5_review_config()
    return config.get_mode_config(mode).human_escalation_enabled


def is_fail_fast_enabled(mode: OperatingMode) -> bool:
    """Check if fail-fast is enabled for operating mode."""
    config = load_phase5_review_config()
    return config.get_mode_config(mode).fail_fast
