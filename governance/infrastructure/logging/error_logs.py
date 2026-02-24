from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.logging.global_error_handler import emit_error_event, resolve_log_path


def _read_only() -> bool:
    return False


def emit_error_event_ssot(**kwargs: Any) -> bool:
    return emit_error_event(**kwargs)


def _update_error_index(*_args: Any, **_kwargs: Any) -> None:
    return None


def resolve_paths_full(config_root: Path | None = None) -> tuple[Path, Path, Path]:
    if config_root is not None:
        cfg = Path(config_root)
        commands = cfg / "commands"
        workspaces = cfg / "workspaces"
        paths_file = commands / "governance.paths.json"
        if paths_file.exists():
            try:
                payload = json.loads(paths_file.read_text(encoding="utf-8"))
                paths = payload.get("paths") if isinstance(payload, dict) else None
                if isinstance(paths, dict):
                    raw_commands = paths.get("commandsHome")
                    raw_workspaces = paths.get("workspacesHome")
                    if isinstance(raw_commands, str) and raw_commands.strip():
                        commands = Path(raw_commands)
                    if isinstance(raw_workspaces, str) and raw_workspaces.strip():
                        workspaces = Path(raw_workspaces)
            except Exception:
                pass
        return cfg, workspaces, commands
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="kernel")
    if evidence.config_root is not None:
        resolved_cfg = evidence.config_root
    elif evidence.commands_home.name == "commands":
        resolved_cfg = evidence.commands_home.parent
    else:
        resolved_cfg = evidence.commands_home
    return resolved_cfg, evidence.workspaces_home, evidence.commands_home


def resolve_ssot_log_path(
    *,
    config_root: Path | str | None = None,
    commands_home: Path | str | None = None,
    workspaces_home: Path | str | None = None,
    repo_fingerprint: str | None = None,
) -> Path:
    cfg = Path(config_root) if isinstance(config_root, str) else config_root
    cmd = Path(commands_home) if isinstance(commands_home, str) else commands_home
    ws = Path(workspaces_home) if isinstance(workspaces_home, str) else workspaces_home
    return resolve_log_path(
        config_root=cfg,
        commands_home=cmd,
        workspaces_home=ws,
        repo_fingerprint=repo_fingerprint,
    )


def write_error_event(
    *,
    reason_key: str,
    message: str,
    config_root: Path | None = None,
    phase: str = "unknown",
    gate: str = "unknown",
    repo_fingerprint: str | None = None,
    command: str = "unknown",
    component: str = "unknown",
    observed_value: Any = None,
    expected_constraint: str | None = None,
    remediation: str | None = None,
    action: str = "block",
    result: str = "blocked",
    details: Any = None,
) -> Path:
    if _read_only() and not str(gate or "").strip():
        raise RuntimeError("diagnostics-read-only")
    cfg, ws, cmd = resolve_paths_full(config_root)
    target = resolve_ssot_log_path(
        config_root=cfg,
        commands_home=cmd,
        workspaces_home=ws,
        repo_fingerprint=repo_fingerprint,
    )
    ok = emit_error_event_ssot(
        severity="CRITICAL" if str(result).lower() == "blocked" else "HIGH",
        code=str(reason_key),
        message=str(message),
        context={
            "gate": gate,
            "mode": "repo-aware",
            "command": command,
            "component": component,
            "observedValue": observed_value,
            "expectedConstraint": expected_constraint,
            "action": action,
            "result": result,
            "remediation": remediation,
            "details": details,
        },
        repo_fingerprint=repo_fingerprint,
        config_root=cfg,
        commands_home=cmd,
        workspaces_home=ws,
        phase=phase,
    )
    if not ok:
        raise RuntimeError("ssot-error-emission-failed")
    return target


def safe_log_error(**kwargs: Any) -> dict[str, str]:
    if _read_only() and not kwargs.get("gate"):
        return {"status": "read-only"}
    try:
        p = write_error_event(**kwargs)
        return {"status": "logged", "path": str(p)}
    except Exception as exc:
        return {"status": "log-failed", "error": str(exc)}
