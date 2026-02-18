from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Literal, Mapping

from governance.infrastructure.path_contract import canonical_config_root, normalize_absolute_path


@dataclass(frozen=True)
class BindingEvidence:
    python_command: str
    cmd_profiles: dict[str, str]
    paths: dict[str, str]
    raw_path: Path | None
    commands_home: Path
    workspaces_home: Path
    governance_paths_json: Path | None
    source: Literal["canonical", "trusted_override", "dev_cwd_search", "missing", "invalid"]
    binding_ok: bool
    audit_marker: str | None


class BindingEvidenceResolver:
    def __init__(self, *, env: Mapping[str, str] | None = None, config_root: Path | None = None):
        self._env = env if env is not None else os.environ
        self._config_root = config_root if config_root is not None else canonical_config_root()

    def _allow_cwd_search(self) -> bool:
        return str(self._env.get("OPENCODE_ALLOW_CWD_BINDINGS", "")).strip() == "1"

    @staticmethod
    def _normalize_path(path: Path) -> Path:
        return Path(os.path.normpath(os.path.abspath(str(path.expanduser()))))

    def _allow_trusted_override(self, *, mode: str, host_caps: Any | None) -> bool:
        if str(mode).strip().lower() == "pipeline":
            return False
        if str(self._env.get("OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE", "")).strip() != "1":
            return False
        if host_caps is None:
            return True
        writable = bool(getattr(host_caps, "fs_write_commands_home", False))
        readable = bool(getattr(host_caps, "fs_read_commands_home", False))
        return writable or readable

    def _trusted_override_candidate(self) -> Path | None:
        raw = str(self._env.get("OPENCODE_TRUSTED_COMMANDS_HOME", "")).strip()
        if not raw:
            return None
        try:
            commands_home = normalize_absolute_path(raw, purpose="env:OPENCODE_TRUSTED_COMMANDS_HOME")
        except Exception:
            return None
        return commands_home / "governance.paths.json"

    def _candidates(
        self,
        *,
        mode: str,
        host_caps: Any | None,
    ) -> list[tuple[Path, Literal["canonical", "trusted_override", "dev_cwd_search"]]]:
        root = self._config_root
        candidates: list[tuple[Path, Literal["canonical", "trusted_override", "dev_cwd_search"]]] = [
            (root / "commands" / "governance.paths.json", "canonical")
        ]
        if self._allow_trusted_override(mode=mode, host_caps=host_caps):
            trusted = self._trusted_override_candidate()
            if trusted is not None:
                candidates.insert(0, (trusted, "trusted_override"))
        if str(mode).strip().lower() != "pipeline" and self._allow_cwd_search():
            cwd = self._normalize_path(Path.cwd())
            candidates.extend(
                (parent / "commands" / "governance.paths.json", "dev_cwd_search")
                for parent in (cwd, *cwd.parents)
            )
        return candidates

    def resolve(self, *, mode: str = "user", host_caps: Any | None = None) -> BindingEvidence:
        root = self._config_root
        commands_home = root / "commands"
        workspaces_home = root / "workspaces"
        python_command = "py -3" if os.name == "nt" else "python3"

        binding_file: Path | None = None
        binding_source: Literal["canonical", "trusted_override", "dev_cwd_search", "missing", "invalid"] = "missing"
        for candidate, source in self._candidates(mode=mode, host_caps=host_caps):
            normalized = self._normalize_path(candidate)
            if normalized.exists():
                binding_file = normalized
                binding_source = source
                break

        if binding_file is None:
            return BindingEvidence(
                python_command=python_command,
                cmd_profiles={},
                paths={},
                raw_path=None,
                commands_home=commands_home,
                workspaces_home=workspaces_home,
                governance_paths_json=None,
                source="missing",
                binding_ok=False,
                audit_marker=None,
            )

        try:
            payload = json.loads(binding_file.read_text(encoding="utf-8"))
            paths = payload.get("paths") if isinstance(payload, dict) else None
            if not isinstance(paths, dict):
                raise ValueError("paths missing")
            if payload.get("schema") != "governance.paths.v1":
                raise ValueError("schema invalid")
            commands = normalize_absolute_path(str(paths.get("commandsHome", "")), purpose="paths.commandsHome")
            workspaces = normalize_absolute_path(str(paths.get("workspacesHome", "")), purpose="paths.workspacesHome")
            cmd_profiles_raw = payload.get("commandProfiles") if isinstance(payload, dict) else None
            cmd_profiles = cmd_profiles_raw if isinstance(cmd_profiles_raw, dict) else {}
            resolved_paths = {
                "commandsHome": str(commands),
                "workspacesHome": str(workspaces),
            }
            raw_python = paths.get("pythonCommand")
            if isinstance(raw_python, str) and raw_python.strip():
                python_command = raw_python.strip()
        except Exception:
            return BindingEvidence(
                python_command=python_command,
                cmd_profiles={},
                paths={},
                raw_path=binding_file,
                commands_home=commands_home,
                workspaces_home=workspaces_home,
                governance_paths_json=binding_file,
                source="invalid",
                binding_ok=False,
                audit_marker=None,
            )

        audit_marker = "POLICY_PRECEDENCE_APPLIED" if binding_source != "canonical" else None
        return BindingEvidence(
            python_command=python_command,
            cmd_profiles={str(k): str(v) for k, v in cmd_profiles.items()},
            paths=resolved_paths,
            raw_path=binding_file,
            commands_home=commands,
            workspaces_home=workspaces,
            governance_paths_json=binding_file,
            source=binding_source,
            binding_ok=True,
            audit_marker=audit_marker,
        )
