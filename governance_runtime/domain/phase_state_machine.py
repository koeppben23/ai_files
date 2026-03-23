from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, cast
import re


PhaseToken = Literal[
    "1",
    "1.1",
    "1.2",
    "1.3",
    "1.5",
    "2",
    "2.1",
    "3A",
    "3B-1",
    "3B-2",
    "4",
    "5",
    "5.3",
    "5.4",
    "5.5",
    "5.6",
    "6",
    "unknown",
]


_PHASE_TOKEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("3B-2", r"^3B-2"),
    ("3B-1", r"^3B-1"),
    ("3A", r"^3A"),
    ("2.1", r"^2\.1"),
    ("1.5", r"^1\.5"),
    ("1.3", r"^1\.3"),
    ("1.2", r"^1\.2"),
    ("1.1", r"^1\.1"),
    ("6", r"^6(?:\b|-)"),
    ("5.6", r"^5\.6"),
    ("5.5", r"^5\.5"),
    ("5.4", r"^5\.4"),
    ("5.3", r"^5\.3"),
    ("5", r"^5(?:\b|-)"),
    ("4", r"^4(?:\b|-)"),
    ("2", r"^2(?:\b|-)"),
    ("1", r"^1(?:\b|-)"),
)


@dataclass(frozen=True)
class EnginePhaseState:
    phase: str
    active_gate: str
    mode: str
    next_gate_condition: str


@dataclass(frozen=True)
class PhaseActionPolicy:
    phase_token: PhaseToken
    ticket_required_allowed: bool


def normalize_phase_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().upper()
    if not normalized:
        return ""
    for token, pattern in _PHASE_TOKEN_PATTERNS:
        if re.match(pattern, normalized):
            return token
    return ""


def phase_requires_ticket_input(phase_token: str) -> bool:
    match = re.match(r"^(\d+)", phase_token)
    if match is None:
        return False
    return int(match.group(1)) >= 4


def resolve_phase_policy(phase_value: object) -> PhaseActionPolicy:
    token = normalize_phase_token(phase_value)
    if not token:
        return PhaseActionPolicy(phase_token="unknown", ticket_required_allowed=False)
    return PhaseActionPolicy(
        phase_token=cast(PhaseToken, token),
        ticket_required_allowed=phase_requires_ticket_input(token),
    )


def build_phase_state(
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
) -> EnginePhaseState:
    return EnginePhaseState(
        phase=phase.strip(),
        active_gate=active_gate.strip(),
        mode=mode.strip(),
        next_gate_condition=next_gate_condition.strip(),
    )


def transition_phase_state(
    current: EnginePhaseState,
    *,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
) -> EnginePhaseState:
    candidate = build_phase_state(
        phase=phase,
        active_gate=active_gate,
        mode=mode,
        next_gate_condition=next_gate_condition,
    )
    if candidate == current:
        return current
    return candidate


# ---------------------------------------------------------------------------
# Canonical phase rank map (single source of truth)
# ---------------------------------------------------------------------------
PHASE_RANK: dict[str, int] = {
    "1": 10,
    "1.1": 11,
    "1.2": 12,
    "1.3": 13,
    "1.5": 15,
    "2": 20,
    "2.1": 21,
    "3A": 30,
    "3B-1": 31,
    "3B-2": 32,
    "4": 40,
    "5": 50,
    "5.3": 53,
    "5.4": 54,
    "5.5": 55,
    "5.6": 56,
    "6": 60,
}


def phase_rank(token: str) -> int:
    """Return the numeric rank for a phase token, or -1 if unknown."""
    return PHASE_RANK.get(token, -1)


# ---------------------------------------------------------------------------
# Phase output policy (loaded from phase_api.yaml SSOT)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanDiscipline:
    first_output_is_draft: bool = False
    draft_not_review_ready: bool = False
    min_self_review_iterations: int = 0


@dataclass(frozen=True)
class PhaseOutputPolicy:
    allowed_output_classes: tuple[str, ...]
    forbidden_output_classes: tuple[str, ...]
    plan_discipline: PlanDiscipline = field(default_factory=PlanDiscipline)


_PHASE_OUTPUT_POLICY_CACHE: dict[str, PhaseOutputPolicy | None] = {}
_PHASE_API_RAW_CACHE: dict[str, Any] = {}

# Pluggable loader for phase_api.yaml phases data.
# Infrastructure layer sets this via set_phase_api_loader().
# Returns list of phase entry mappings from phase_api.yaml.
_phase_api_loader: Callable[[], list[Mapping[str, Any]]] | None = None


def set_phase_api_loader(loader: Callable[[], list[Mapping[str, Any]]]) -> None:
    """Register infrastructure-provided loader for phase_api.yaml phases data."""
    global _phase_api_loader
    _phase_api_loader = loader
    # Invalidate cache when loader changes
    _PHASE_OUTPUT_POLICY_CACHE.clear()
    _PHASE_API_RAW_CACHE.clear()


def _load_phase_api_raw() -> list[Mapping[str, Any]]:
    """Load phases list via registered loader.  Cached after first call."""
    if "phases" in _PHASE_API_RAW_CACHE:
        return _PHASE_API_RAW_CACHE["phases"]

    global _phase_api_loader
    if _phase_api_loader is None:
        # Auto-configure from infrastructure layer on first access
        try:
            from governance_runtime.infrastructure.phase_api_output_policy_loader import configure_phase_output_policy_loader
            configure_phase_output_policy_loader()
        except ImportError:
            pass

    if _phase_api_loader is None:
        _PHASE_API_RAW_CACHE["phases"] = []
        return []

    phases = _phase_api_loader()
    _PHASE_API_RAW_CACHE["phases"] = phases
    return phases


def _parse_output_policy(raw: Mapping[str, Any]) -> PhaseOutputPolicy:
    """Parse an output_policy block from a phase entry."""
    allowed = raw.get("allowed_output_classes", ())
    forbidden = raw.get("forbidden_output_classes", ())
    pd_raw = raw.get("plan_discipline", {})
    plan_discipline = PlanDiscipline(
        first_output_is_draft=bool(pd_raw.get("first_output_is_draft", False)),
        draft_not_review_ready=bool(pd_raw.get("draft_not_review_ready", False)),
        min_self_review_iterations=int(pd_raw.get("min_self_review_iterations", 0)),
    )
    return PhaseOutputPolicy(
        allowed_output_classes=tuple(str(c).strip() for c in allowed),
        forbidden_output_classes=tuple(str(c).strip() for c in forbidden),
        plan_discipline=plan_discipline,
    )


def resolve_phase_output_policy(phase_token: str) -> PhaseOutputPolicy | None:
    """Resolve output policy for a phase token from phase_api.yaml.

    Inheritance: 5.* tokens inherit from token "5" unless they define their
    own output_policy.  Returns None if no output_policy exists for the token.
    """
    if phase_token in _PHASE_OUTPUT_POLICY_CACHE:
        return _PHASE_OUTPUT_POLICY_CACHE[phase_token]

    phases = _load_phase_api_raw()
    # Build token -> output_policy map
    token_policy_raw: dict[str, Mapping[str, Any]] = {}
    for entry in phases:
        if not isinstance(entry, Mapping):
            continue
        tok = str(entry.get("token", "")).strip()
        op = entry.get("output_policy")
        if tok and isinstance(op, Mapping):
            token_policy_raw[tok] = op

    # Direct lookup
    if phase_token in token_policy_raw:
        policy = _parse_output_policy(token_policy_raw[phase_token])
        _PHASE_OUTPUT_POLICY_CACHE[phase_token] = policy
        return policy

    # Inheritance: 5.* inherits from "5"
    match = re.match(r"^(\d+)\.", phase_token)
    if match:
        parent_token = match.group(1)
        if parent_token in token_policy_raw:
            policy = _parse_output_policy(token_policy_raw[parent_token])
            _PHASE_OUTPUT_POLICY_CACHE[phase_token] = policy
            return policy

    _PHASE_OUTPUT_POLICY_CACHE[phase_token] = None
    return None


def clear_phase_output_policy_cache() -> None:
    """Clear cached output policy data (for testing)."""
    _PHASE_OUTPUT_POLICY_CACHE.clear()
    _PHASE_API_RAW_CACHE.clear()

