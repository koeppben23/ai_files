from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


class PhaseApiSpecError(RuntimeError):
    pass


@dataclass(frozen=True)
class TransitionRule:
    when: str
    next_token: str
    source: str = "spec-transition"
    active_gate: str | None = None
    next_gate_condition: str | None = None


@dataclass(frozen=True)
class PhaseSpecEntry:
    token: str
    phase: str
    active_gate: str
    next_gate_condition: str
    next_token: str | None
    route_strategy: str
    transitions: tuple[TransitionRule, ...]
    exit_required_keys: tuple[str, ...]


@dataclass(frozen=True)
class PhaseApiSpec:
    path: Path
    sha256: str
    stable_hash: str
    loaded_at: str
    start_token: str
    entries: dict[str, PhaseSpecEntry]


def _resolve_phase_api_path(commands_home: Path) -> Path:
    return commands_home / "phase_api.yaml"


def _phase_rank(token: str) -> tuple[int, str]:
    numeric = token.upper().replace("B", ".2").replace("A", ".1").replace("-", ".")
    parts: list[int] = []
    for piece in numeric.split("."):
        piece = piece.strip()
        if not piece:
            continue
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(999)
    return (parts[0] if parts else 999, token)


def _parse_transition(raw: Mapping[str, Any]) -> TransitionRule:
    when = str(raw.get("when", "")).strip()
    next_token = str(raw.get("next", "")).strip().upper()
    if not when:
        raise PhaseApiSpecError("phase_api.yaml transition missing 'when'")
    if not next_token:
        raise PhaseApiSpecError("phase_api.yaml transition missing 'next'")
    source = str(raw.get("source", "spec-transition")).strip() or "spec-transition"
    active_gate = raw.get("active_gate")
    next_gate_condition = raw.get("next_gate_condition")
    return TransitionRule(
        when=when,
        next_token=next_token,
        source=source,
        active_gate=str(active_gate).strip() if isinstance(active_gate, str) else None,
        next_gate_condition=str(next_gate_condition).strip() if isinstance(next_gate_condition, str) else None,
    )


def _parse_entry(raw: Mapping[str, Any]) -> PhaseSpecEntry:
    token = str(raw.get("token", "")).strip().upper()
    phase = str(raw.get("phase", "")).strip()
    active_gate = str(raw.get("active_gate", "")).strip()
    next_gate_condition = str(raw.get("next_gate_condition", "")).strip()
    next_token_raw = str(raw.get("next", "")).strip().upper()
    next_token = next_token_raw or None
    route_strategy = str(raw.get("route_strategy", "stay")).strip().lower() or "stay"
    if not token:
        raise PhaseApiSpecError("phase_api.yaml entry missing token")
    if not phase:
        raise PhaseApiSpecError(f"phase_api.yaml token {token}: missing phase")
    if route_strategy not in {"stay", "next"}:
        raise PhaseApiSpecError(f"phase_api.yaml token {token}: route_strategy must be stay|next")
    transitions_raw = raw.get("transitions", [])
    transitions: list[TransitionRule] = []
    if transitions_raw is not None:
        if not isinstance(transitions_raw, list):
            raise PhaseApiSpecError(f"phase_api.yaml token {token}: transitions must be a list")
        for row in transitions_raw:
            if not isinstance(row, Mapping):
                raise PhaseApiSpecError(f"phase_api.yaml token {token}: transition rows must be objects")
            transitions.append(_parse_transition(row))
    exit_required_keys_raw = raw.get("exit_required_keys", [])
    exit_required_keys: list[str] = []
    if exit_required_keys_raw is not None:
        if not isinstance(exit_required_keys_raw, list):
            raise PhaseApiSpecError(f"phase_api.yaml token {token}: exit_required_keys must be a list")
        for key in exit_required_keys_raw:
            if not isinstance(key, str) or not key.strip():
                raise PhaseApiSpecError(f"phase_api.yaml token {token}: invalid exit_required_keys value")
            exit_required_keys.append(key.strip())
    return PhaseSpecEntry(
        token=token,
        phase=phase,
        active_gate=active_gate,
        next_gate_condition=next_gate_condition,
        next_token=next_token,
        route_strategy=route_strategy,
        transitions=tuple(transitions),
        exit_required_keys=tuple(exit_required_keys),
    )


def _stable_hash(entries: Mapping[str, PhaseSpecEntry], start_token: str) -> str:
    payload = {
        "start_token": start_token,
        "entries": [
            {
                "token": entry.token,
                "phase": entry.phase,
                "active_gate": entry.active_gate,
                "next_gate_condition": entry.next_gate_condition,
                "next_token": entry.next_token,
                "route_strategy": entry.route_strategy,
                "exit_required_keys": list(entry.exit_required_keys),
                "transitions": [
                    {
                        "when": tr.when,
                        "next": tr.next_token,
                        "source": tr.source,
                        "active_gate": tr.active_gate,
                        "next_gate_condition": tr.next_gate_condition,
                    }
                    for tr in entry.transitions
                ],
            }
            for _, entry in sorted(entries.items(), key=lambda kv: _phase_rank(kv[0]))
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_links(entries: Mapping[str, PhaseSpecEntry]) -> None:
    tokens = set(entries.keys())
    for entry in entries.values():
        if entry.next_token is not None and entry.next_token not in tokens:
            raise PhaseApiSpecError(f"phase_api.yaml token {entry.token}: unknown next token {entry.next_token}")
        for transition in entry.transitions:
            if transition.next_token not in tokens:
                raise PhaseApiSpecError(
                    f"phase_api.yaml token {entry.token}: unknown transition next token {transition.next_token}"
                )


def _resolve_commands_home(explicit_commands_home: Path | None) -> Path:
    if explicit_commands_home is not None:
        return explicit_commands_home
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="kernel")
    if not evidence.binding_ok:
        raise PhaseApiSpecError(
            "binding evidence invalid or missing for commands home resolution"
            + (f": {', '.join(evidence.issues)}" if evidence.issues else "")
        )
    return evidence.commands_home


def load_phase_api(commands_home: Path | None = None) -> PhaseApiSpec:
    if yaml is None:
        raise PhaseApiSpecError("phase_api.yaml cannot be loaded: yaml parser unavailable")

    resolved_commands_home = _resolve_commands_home(commands_home)
    phase_api_path = _resolve_phase_api_path(resolved_commands_home)
    if not phase_api_path.exists():
        raise PhaseApiSpecError(f"phase_api.yaml missing at {phase_api_path}")

    raw_text = phase_api_path.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    try:
        payload = yaml.safe_load(raw_text)
    except Exception as exc:
        raise PhaseApiSpecError(f"phase_api.yaml invalid yaml at {phase_api_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise PhaseApiSpecError("phase_api.yaml must be a mapping")
    phases = payload.get("phases")
    if not isinstance(phases, list) or not phases:
        raise PhaseApiSpecError("phase_api.yaml must define non-empty phases list")

    entries: dict[str, PhaseSpecEntry] = {}
    for row in phases:
        if not isinstance(row, Mapping):
            raise PhaseApiSpecError("phase_api.yaml phases must contain objects")
        entry = _parse_entry(row)
        if entry.token in entries:
            raise PhaseApiSpecError(f"phase_api.yaml duplicate token {entry.token}")
        entries[entry.token] = entry

    _validate_links(entries)

    start_token = str(payload.get("start_token", "")).strip().upper()
    if not start_token:
        raise PhaseApiSpecError("phase_api.yaml start_token missing")
    if start_token not in entries:
        raise PhaseApiSpecError(f"phase_api.yaml start_token {start_token} not defined")

    stable_hash = _stable_hash(entries, start_token)
    return PhaseApiSpec(
        path=phase_api_path,
        sha256=source_hash,
        stable_hash=stable_hash,
        loaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        start_token=start_token,
        entries=entries,
    )
