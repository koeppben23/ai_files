"""Phase 4 Self-Review Mechanism.

Kernel-enforced internal self-review for Phase 4 plans:
- Rigor levels mapped to complexity class (DETERMINISTIC)
- Mode-aware behavior (pipeline/user/agents_strict)
- Evidence generation for audit trail
- Pipeline: 0 prompts enforced, human assist HARD-DISABLED

Contract:
- Self-review rounds are kernel-managed, internal (no prompts)
- MD lists required evidence artifacts; schemas validated by embedded registry
- Policy-bound config: pack-locked, changes audited
- Complexity classification from deterministic signals, NOT LLM estimation
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Sequence, Any, Protocol, runtime_checkable

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore
    YAML_AVAILABLE = False


RigorLevel = Literal["minimal", "standard", "maximum"]
ReviewStatus = Literal["pass", "pass-with-notes", "fail"]
FindingSeverity = Literal["info", "warning", "critical"]
FinalReviewStatus = Literal["approved", "needs-revision", "second-pass-triggered", "blocked-pipeline-interactive"]
OperatingMode = Literal["user", "pipeline", "agents_strict"]


# Pipeline Hard-Block Reason Codes
PIPELINE_BLOCK_REASONS = {
    "interactive_prompt_required": "BLOCKED-PIPELINE-INTERACTIVE",
    "human_assist_required": "BLOCKED-PIPELINE-HUMAN-ASSIST",
}


@runtime_checkable
class ConfigPathResolver(Protocol):
    """Protocol for resolving config path (Dependency Inversion)."""
    def resolve_config_path(self) -> Path | None:
        """Resolve path to policy-bound config, or None if unavailable."""
        ...
    
    def allow_repo_local_fallback(self) -> bool:
        """Check if repo-local fallback is allowed (dev/test opt-in)."""
        ...

    def operating_mode(self) -> str:
        """Return effective operating mode bound by infrastructure wiring."""
        ...


# Default resolver is set at runtime from infrastructure layer
# This avoids application → infrastructure import violation
_default_resolver: ConfigPathResolver | None = None


def set_config_path_resolver(resolver: ConfigPathResolver) -> None:
    """Set config path resolver (called from infrastructure at startup)."""
    global _default_resolver
    _default_resolver = resolver


def get_config_path_resolver() -> ConfigPathResolver:
    """Get current resolver or raise if not configured."""
    if _default_resolver is None:
        raise PolicyConfigError(
            "ConfigPathResolver not configured. "
            "Call set_config_path_resolver() at startup. "
            "Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    return _default_resolver


@dataclass(frozen=True)
class ReviewFinding:
    """A single finding from a self-review round."""
    category: str
    severity: FindingSeverity
    message: str
    location: str = ""
    remediation: str = ""
    
    @property
    def is_blocking(self) -> bool:
        return self.severity == "critical"
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "location": self.location,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class SelfReviewRound:
    """Evidence from a single self-review round."""
    round_index: int
    focus: str
    findings: tuple[ReviewFinding, ...]
    blocking_findings: tuple[ReviewFinding, ...]
    status: ReviewStatus
    plan_hash_before: str = ""
    plan_hash_after: str = ""
    
    @property
    def has_blocking(self) -> bool:
        return len(self.blocking_findings) > 0
    
    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "focus": self.focus,
            "findings": [f.to_dict() for f in self.findings],
            "blocking_findings": [f.to_dict() for f in self.blocking_findings],
            "status": self.status,
            "plan_hash_before": self.plan_hash_before,
            "plan_hash_after": self.plan_hash_after,
        }


@dataclass(frozen=True)
class SelfReviewState:
    """Complete state of Phase 4 self-review."""
    complexity_class: str
    rigor_level: RigorLevel
    operating_mode: str
    rounds: tuple[SelfReviewRound, ...]
    rounds_completed: int
    total_rounds: int
    critical_triggered_second_pass: bool = False
    final_status: FinalReviewStatus = "approved"
    max_cycles: int = 2
    current_cycle: int = 1
    
    @property
    def can_continue(self) -> bool:
        """Check if more rounds are possible."""
        if self.rounds_completed >= self.total_rounds:
            return False
        if self.final_status == "second-pass-triggered" and self.current_cycle >= self.max_cycles:
            return False
        return True
    
    @property
    def current_round_number(self) -> int:
        """Get current round number (1-indexed)."""
        return self.rounds_completed + 1
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "complexity_class": self.complexity_class,
            "rigor_level": self.rigor_level,
            "operating_mode": self.operating_mode,
            "rounds": [r.to_dict() for r in self.rounds],
            "rounds_completed": self.rounds_completed,
            "total_rounds": self.total_rounds,
            "critical_triggered_second_pass": self.critical_triggered_second_pass,
            "final_status": self.final_status,
            "max_cycles": self.max_cycles,
            "current_cycle": self.current_cycle,
        }


@dataclass(frozen=True)
class SelfReviewConfig:
    """Configuration for self-review (policy-bound, pack-locked)."""
    rounds_for_rigor: dict[str, int] = field(default_factory=lambda: {
        "minimal": 1,
        "standard": 3,
        "maximum": 3,
    })
    second_pass_on_critical: dict[str, bool] = field(default_factory=lambda: {
        "minimal": False,
        "standard": True,
        "maximum": True,
    })
    max_cycles_for_mode: dict[str, int] = field(default_factory=lambda: {
        "user": 2,
        "pipeline": 2,
        "agents_strict": 1,
    })
    complexity_to_rigor: dict[str, str] = field(default_factory=lambda: {
        "SIMPLE-CRUD": "minimal",
        "REFACTORING": "standard",
        "MODIFICATION": "standard",
        "COMPLEX": "maximum",
        "STANDARD": "standard",
    })
    critical_issue_types: tuple[str, ...] = (
        "security_vulnerability",
        "data_loss_risk",
        "breaking_change_without_migration",
        "compliance_violation",
    )
    # Pipeline hard-block settings
    pipeline_human_assist_allowed: bool = False
    pipeline_prompt_budget_check: str = "hard"


@dataclass(frozen=True)
class ComplexitySignals:
    """Deterministic signals for complexity classification."""
    files_changed: int = 0
    loc_changed: int = 0
    public_api_changed: bool = False
    schema_migration: bool = False
    security_paths_touched: bool = False
    permissions_changed: bool = False
    network_io_changed: bool = False
    test_coverage_delta: float = 0.0


_CONFIG_CACHE: SelfReviewConfig | None = None


class PolicyConfigError(Exception):
    """Raised when policy-bound config is missing or invalid."""
    pass


def _get_repo_local_config_path() -> Path:
    """Get repo-local config path as fallback.
    
    This is used when canonical root is not available (dev/test environments).
    Uses string manipulation instead of resolve() to avoid side effects.
    """
    # Navigate from this file to repo root without resolve()
    # __file__ = .../governance/application/use_cases/phase4_self_review.py
    # repo root = 4 levels up
    parts = Path(__file__).parts
    # Find governance index and go 1 level up
    if "governance" in parts:
        gov_idx = parts.index("governance")
        repo_root = Path(*parts[:gov_idx])
        return repo_root / "diagnostics" / "phase4_self_review_config.yaml"
    # Fallback
    return Path(__file__).parent.parent.parent.parent / "diagnostics" / "phase4_self_review_config.yaml"


def load_self_review_config(*, force_reload: bool = False) -> SelfReviewConfig:
    """Load policy-bound self-review config.
    
    Policy Contract:
    - Config is pack-locked, part of engine_master_policy
    - Missing/invalid config → BLOCKED_ENGINE_SELFCHECK (fail-closed)
    - No silent fallback to defaults for policy-bound settings
    - Path resolved via injected resolver (Dependency Inversion)
    - Fallback to repo-local path for dev/test environments
    
    Raises:
        PolicyConfigError: If policy-bound config is missing or invalid
    """
    global _CONFIG_CACHE
    
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE
    
    # Try injected resolver first (SSOT via Dependency Inversion)
    config_path = None
    resolver_source = "none"
    if _default_resolver is not None:
        config_path = _default_resolver.resolve_config_path()
        resolver_source = "injected_resolver"
    
    # Check if repo-local fallback is allowed
    # Either through resolver method or direct env check (when no resolver)
    allow_repo_local = False
    effective_mode = "user"
    if _default_resolver is not None and hasattr(_default_resolver, "operating_mode"):
        try:
            effective_mode = str(_default_resolver.operating_mode()).strip().lower() or "user"
        except Exception:
            effective_mode = "user"

    if effective_mode != "pipeline" and _default_resolver is not None and hasattr(_default_resolver, "allow_repo_local_fallback"):
        allow_repo_local = _default_resolver.allow_repo_local_fallback()
    
    # Fallback to repo-local path ONLY with explicit opt-in (dev/test)
    if config_path is None:
        if allow_repo_local:
            config_path = _get_repo_local_config_path()
            resolver_source = "repo_local_opt_in"
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
            f"Expected pack-locked config at canonical root or repo-local diagnostics/. "
            f"Reason: BLOCKED-ENGINE-SELFCHECK"
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
            f"Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    
    if not data:
        raise PolicyConfigError(
            f"Policy-bound config is empty: {config_path}. "
            f"Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    
    # Validate policy metadata (pack-locked, precedence)
    policy = data.get("policy", {})
    if policy.get("pack_locked") is not True:
        raise PolicyConfigError(
            f"Policy-bound config must have pack_locked=true. "
            f"Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    
    expected_precedence = "engine_master_policy"
    if policy.get("precedence_level") != expected_precedence:
        raise PolicyConfigError(
            f"Policy-bound config has wrong precedence_level. "
            f"Expected: {expected_precedence}, got: {policy.get('precedence_level')}. "
            f"Reason: BLOCKED-ENGINE-SELFCHECK"
        )
    
    rigor_levels = data.get("rigor_levels", {})
    modes = data.get("modes", {})
    mapping = data.get("complexity_mapping", {})
    
    _CONFIG_CACHE = SelfReviewConfig(
        rounds_for_rigor={
            k: v.get("rounds", 3) for k, v in rigor_levels.items()
        },
        second_pass_on_critical={
            k: v.get("second_pass_on_critical", True) for k, v in rigor_levels.items()
        },
        max_cycles_for_mode={
            k: v.get("max_cycles", 2) for k, v in modes.items()
        },
        complexity_to_rigor=mapping,
        critical_issue_types=tuple(data.get("critical_issue_types", [])),
        pipeline_human_assist_allowed=modes.get("pipeline", {}).get("human_assist_allowed", False),
        pipeline_prompt_budget_check=modes.get("pipeline", {}).get("prompt_budget_check", "hard"),
    )
    
    return _CONFIG_CACHE


def classify_complexity_from_signals(signals: ComplexitySignals) -> str:
    """Classify complexity from DETERMINISTIC signals (not LLM estimation).
    
    Policy: Classification MUST be derived from measurable signals.
    - files_changed, loc_changed: git diff stats
    - public_api_changed: paths matching api/routes/controllers
    - schema_migration: paths matching migrations/schema
    - security_paths_touched: paths matching auth/security/crypto
    - permissions_changed: paths matching permission/rbac
    - network_io_changed: paths matching network/http/grpc
    - test_coverage_delta: coverage report comparison
    """
    # COMPLEX: Any high-risk signal triggers maximum rigor
    if any([
        signals.public_api_changed,
        signals.schema_migration,
        signals.security_paths_touched,
        signals.permissions_changed,
        signals.network_io_changed,
        signals.files_changed > 10,
        signals.loc_changed > 500,
        signals.test_coverage_delta < -5.0,
    ]):
        return "COMPLEX"
    
    # SIMPLE-CRUD: Very small, no risk signals
    if all([
        signals.files_changed <= 3,
        signals.loc_changed <= 100,
        not signals.public_api_changed,
        not signals.schema_migration,
        not signals.security_paths_touched,
    ]):
        return "SIMPLE-CRUD"
    
    # STANDARD: Default for moderate changes
    return "STANDARD"


def check_pipeline_constraints(
    operating_mode: OperatingMode,
    requires_human_assist: bool = False,
    requires_interactive_prompt: bool = False,
) -> tuple[bool, str]:
    """Check if pipeline mode constraints are violated.
    
    Returns: (is_blocked, reason_code)
    
    Pipeline mode:
    - 0 prompts enforced (hard)
    - human_assist HARD-DISABLED
    - Any interactive requirement → BLOCKED-PIPELINE-INTERACTIVE
    """
    if operating_mode != "pipeline":
        return (False, "")
    
    if requires_human_assist:
        return (True, PIPELINE_BLOCK_REASONS["human_assist_required"])
    
    if requires_interactive_prompt:
        return (True, PIPELINE_BLOCK_REASONS["interactive_prompt_required"])
    
    return (False, "")


def create_self_review_state(
    complexity_class: str,
    operating_mode: str = "user",
) -> SelfReviewState:
    """Create initial self-review state based on complexity class."""
    config = load_self_review_config()
    
    rigor_raw = config.complexity_to_rigor.get(complexity_class, "standard")
    rigor: RigorLevel = rigor_raw if rigor_raw in ("minimal", "standard", "maximum") else "standard"
    total_rounds = config.rounds_for_rigor.get(rigor, 3)
    max_cycles = config.max_cycles_for_mode.get(operating_mode, 2)
    
    return SelfReviewState(
        complexity_class=complexity_class,
        rigor_level=rigor,
        operating_mode=operating_mode,
        rounds=(),
        rounds_completed=0,
        total_rounds=total_rounds,
        max_cycles=max_cycles,
        current_cycle=1,
    )


def record_review_round(
    state: SelfReviewState,
    *,
    focus: str,
    findings: Sequence[ReviewFinding],
    plan_hash_before: str = "",
    plan_hash_after: str = "",
) -> SelfReviewState:
    """Record a completed review round and determine next state."""
    config = load_self_review_config()
    
    blocking = tuple(f for f in findings if f.is_blocking)
    
    # Determine round status
    if blocking:
        status: ReviewStatus = "fail"
    elif any(f.severity == "warning" for f in findings):
        status = "pass-with-notes"
    else:
        status = "pass"
    
    round_obj = SelfReviewRound(
        round_index=state.rounds_completed + 1,
        focus=focus,
        findings=tuple(findings),
        blocking_findings=blocking,
        status=status,
        plan_hash_before=plan_hash_before,
        plan_hash_after=plan_hash_after,
    )
    
    new_rounds = state.rounds + (round_obj,)
    new_rounds_completed = state.rounds_completed + 1
    
    # Determine if second pass should be triggered
    critical_found = any(
        f.category in config.critical_issue_types
        for f in findings
        if f.severity == "critical"
    )
    
    should_trigger_second_pass = (
        critical_found
        and config.second_pass_on_critical.get(state.rigor_level, True)
        and new_rounds_completed >= state.total_rounds
        and state.current_cycle < state.max_cycles
    )
    
    if should_trigger_second_pass:
        return SelfReviewState(
            complexity_class=state.complexity_class,
            rigor_level=state.rigor_level,
            operating_mode=state.operating_mode,
            rounds=new_rounds,
            rounds_completed=0,  # Reset for second pass
            total_rounds=state.total_rounds,
            critical_triggered_second_pass=True,
            final_status="second-pass-triggered",
            max_cycles=state.max_cycles,
            current_cycle=state.current_cycle + 1,
        )
    
    # Determine final status
    if new_rounds_completed >= state.total_rounds:
        if blocking:
            final_status: FinalReviewStatus = "needs-revision"
        else:
            final_status = "approved"
    else:
        final_status = "approved"  # More rounds pending
    
    return SelfReviewState(
        complexity_class=state.complexity_class,
        rigor_level=state.rigor_level,
        operating_mode=state.operating_mode,
        rounds=new_rounds,
        rounds_completed=new_rounds_completed,
        total_rounds=state.total_rounds,
        critical_triggered_second_pass=state.critical_triggered_second_pass,
        final_status=final_status,
        max_cycles=state.max_cycles,
        current_cycle=state.current_cycle,
    )


def get_focus_area(state: SelfReviewState) -> str:
    """Get the focus area for the current round."""
    focus_areas = {
        "minimal": ["correctness"],
        "standard": ["correctness", "completeness", "robustness"],
        "maximum": ["correctness", "completeness", "robustness", "security", "production-readiness"],
    }
    
    areas = focus_areas.get(state.rigor_level, focus_areas["standard"])
    
    if state.current_round_number <= len(areas):
        return areas[state.current_round_number - 1]
    
    return "completeness"


def format_review_summary(state: SelfReviewState) -> str:
    """Format human-readable review summary."""
    lines = [
        "## Phase 4 Self-Review Summary",
        "",
        f"- **Complexity Class:** {state.complexity_class}",
        f"- **Rigor Level:** {state.rigor_level}",
        f"- **Operating Mode:** {state.operating_mode}",
        f"- **Rounds Completed:** {state.rounds_completed}/{state.total_rounds}",
        f"- **Current Cycle:** {state.current_cycle}/{state.max_cycles}",
        f"- **Final Status:** {state.final_status}",
    ]
    
    if state.critical_triggered_second_pass:
        lines.append("- **Second Pass Triggered:** Yes (critical issues found)")
    
    if state.rounds:
        lines.append("")
        lines.append("### Rounds")
        
        for r in state.rounds:
            lines.append(f"")
            lines.append(f"**Round {r.round_index}** ({r.focus}): `{r.status}`")
            
            if r.findings:
                lines.append(f"- Total Findings: {len(r.findings)}")
                lines.append(f"- Blocking: {len(r.blocking_findings)}")
            
            if r.blocking_findings:
                for f in r.blocking_findings[:3]:
                    lines.append(f"  - [{f.severity}] {f.message}")
    
    return "\n".join(lines)
