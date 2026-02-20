"""Phase 5 Review Configuration Loader.

Policy-bound SSOT loader for Phase 5 iterative review settings.
Missing/invalid config is fail-closed.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore
    YAML_AVAILABLE = False


OperatingMode = Literal["user", "pipeline", "agents_strict"]
PipelineFallback = Literal["reject", "approve_with_warnings"]


@runtime_checkable
class ConfigPathResolver(Protocol):
    """Protocol for resolving policy config path."""

    def resolve_config_path(self) -> Path | None:
        ...

    def allow_repo_local_fallback(self) -> bool:
        ...

    def operating_mode(self) -> str:
        ...


_default_resolver: ConfigPathResolver | None = None


def set_config_path_resolver(resolver: ConfigPathResolver) -> None:
    global _default_resolver
    _default_resolver = resolver


def get_config_path_resolver() -> ConfigPathResolver:
    if _default_resolver is None:
        raise PolicyConfigError(
            "ConfigPathResolver not configured. "
            "Call set_config_path_resolver() at startup. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    return _default_resolver


class PolicyConfigError(Exception):
    """Raised when policy-bound config is missing or invalid."""


@dataclass(frozen=True)
class ReviewCriteria:
    test_coverage_min_percent: int = 80
    security_scan_required: bool = True
    architecture_doc_required: bool = True
    breaking_changes_documented: bool = True
    rollback_plan_required: bool = False


@dataclass(frozen=True)
class ModeConfig:
    human_escalation_enabled: bool = True
    auto_approve_on_no_issues: bool = True
    auto_reject_on_blocking_issues: bool = False
    max_iterations: int = 3
    fail_fast: bool = False


@dataclass(frozen=True)
class EscalationConfig:
    triggers: tuple[str, ...] = (
        "open_questions_after_max_iterations",
        "unresolved_issues_after_max_iterations",
        "explicit_needs_human_status",
    )
    pipeline_fallback: PipelineFallback = "reject"


@dataclass(frozen=True)
class AuditConfig:
    log_all_feedback: bool = True
    persist_feedback_history: bool = True
    include_timestamps: bool = True
    retention_days: int = 90


@dataclass(frozen=True)
class MetricsConfig:
    track_review_duration: bool = True
    track_issues_per_iteration: bool = True
    track_approval_rate: bool = True


@dataclass(frozen=True)
class Phase5ReviewConfig:
    max_iterations: int = 3
    criteria: ReviewCriteria = field(default_factory=ReviewCriteria)
    modes: dict[str, ModeConfig] = field(
        default_factory=lambda: {
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
        }
    )
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Phase5ReviewConfig":
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
        return self.modes.get(mode, self.modes["user"])


_CONFIG_CACHE: Phase5ReviewConfig | None = None


def _get_repo_local_config_path() -> Path:
    parts = Path(__file__).parts
    if "governance" in parts:
        gov_idx = parts.index("governance")
        repo_root = Path(*parts[:gov_idx])
        return repo_root / "diagnostics" / "phase5_review_config.yaml"
    return Path(__file__).parent.parent.parent.parent / "diagnostics" / "phase5_review_config.yaml"


def load_phase5_review_config(*, force_reload: bool = False) -> Phase5ReviewConfig:
    """Load policy-bound phase5 config (fail-closed)."""
    global _CONFIG_CACHE

    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    config_path = None
    if _default_resolver is not None:
        config_path = _default_resolver.resolve_config_path()

    allow_repo_local = False
    if _default_resolver is not None and hasattr(_default_resolver, "allow_repo_local_fallback"):
        allow_repo_local = _default_resolver.allow_repo_local_fallback()

    effective_mode = "user"
    if _default_resolver is not None and hasattr(_default_resolver, "operating_mode"):
        try:
            effective_mode = str(_default_resolver.operating_mode()).strip().lower() or "user"
        except Exception:
            effective_mode = "user"
    if effective_mode == "pipeline":
        allow_repo_local = False

    if config_path is None:
        if allow_repo_local:
            config_path = _get_repo_local_config_path()
        else:
            hint = (
                "Pipeline mode disallows repo-local fallback. "
                if effective_mode == "pipeline"
                else "Set OPENCODE_ALLOW_REPO_LOCAL_CONFIG=1 for dev/test environments. "
            )
            raise PolicyConfigError(
                "Policy-bound config not resolved via canonical root. "
                + hint
                +
                "Reason: BLOCKED-ENGINE-SELFCHECK"
            )

    if not config_path.exists():
        raise PolicyConfigError(
            f"Policy-bound config missing: {config_path}. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )

    if not YAML_AVAILABLE:
        raise PolicyConfigError(
            "YAML parser not available for policy-bound config. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )

    import yaml as yaml_loader  # type: ignore

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml_loader.safe_load(f)
    except Exception as exc:
        raise PolicyConfigError(
            f"Policy-bound config not parseable: {exc}. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )

    if not data:
        raise PolicyConfigError(
            f"Policy-bound config is empty: {config_path}. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )

    policy = data.get("policy", {})
    if policy.get("pack_locked") is not True:
        raise PolicyConfigError(
            "Policy-bound config must have pack_locked=true. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    if policy.get("precedence_level") != "engine_master_policy":
        raise PolicyConfigError(
            "Policy-bound config has wrong precedence_level. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )

    _CONFIG_CACHE = Phase5ReviewConfig.from_dict(data)
    return _CONFIG_CACHE


def get_max_iterations(mode: OperatingMode) -> int:
    config = load_phase5_review_config()
    return config.get_mode_config(mode).max_iterations


def is_human_escalation_enabled(mode: OperatingMode) -> bool:
    config = load_phase5_review_config()
    return config.get_mode_config(mode).human_escalation_enabled


def is_fail_fast_enabled(mode: OperatingMode) -> bool:
    config = load_phase5_review_config()
    return config.get_mode_config(mode).fail_fast
