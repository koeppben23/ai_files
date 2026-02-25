from __future__ import annotations

import os
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from governance.infrastructure.path_contract import canonical_config_root, normalize_absolute_path


_SUPPORTED_BINDING_SCHEMAS: tuple[str, ...] = (
    "opencode-governance.paths.v1",
    "governance.paths.v1",
)


@dataclass(frozen=True)
class BindingEvidence:
    python_command: str
    cmd_profiles: dict[str, str]
    paths: dict[str, str]
    raw_path: Path | None
    commands_home: Path | None
    workspaces_home: Path | None
    config_root: Path | None
    governance_paths_json: Path | None
    source: Literal["canonical", "missing", "invalid"]
    binding_ok: bool
    issues: list[str]
    audit_marker: str | None
    audit_event: dict[str, object] | None = None


class BindingEvidenceResolver:
    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        config_root: Path | None = None,
        cwd_provider: Callable[[], Path] | None = None,
    ):
        self._env = env if env is not None else {}
        configured_root = config_root if config_root is not None else canonical_config_root()
        self._config_root = normalize_absolute_path(str(configured_root), purpose="resolver.config_root")
        self._cwd_provider = cwd_provider if cwd_provider is not None else Path.cwd

    @staticmethod
    def _parse_command_profiles(value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("commandProfiles invalid")
        out: dict[str, str] = {}
        for raw_key, raw_val in value.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                raise ValueError("commandProfiles key invalid")
            if not isinstance(raw_val, str) or not raw_val.strip():
                raise ValueError("commandProfiles value invalid")
            out[raw_key.strip()] = raw_val.strip()
        return out

    def resolve(self, *, mode: str = "user", host_caps: Any | None = None) -> BindingEvidence:
        _ = mode
        _ = host_caps
        _ = self._cwd_provider

        env_commands_home = self._env.get("COMMANDS_HOME") or os.environ.get("COMMANDS_HOME")
        if env_commands_home:
            try:
                commands_home = normalize_absolute_path(env_commands_home, purpose="COMMANDS_HOME env")
                root = commands_home.parent
                binding_file = commands_home / "governance.paths.json"
                if not binding_file.exists():
                    return BindingEvidence(
                        python_command="",
                        cmd_profiles={},
                        paths={},
                        raw_path=None,
                        commands_home=None,
                        workspaces_home=None,
                        config_root=None,
                        governance_paths_json=None,
                        source="invalid",
                        binding_ok=False,
                        issues=[f"COMMANDS_HOME set but binding file not found: {binding_file}"],
                        audit_marker=None,
                        audit_event=None,
                    )
            except Exception as e:
                return BindingEvidence(
                    python_command="",
                    cmd_profiles={},
                    paths={},
                    raw_path=None,
                    commands_home=None,
                    workspaces_home=None,
                    config_root=None,
                    governance_paths_json=None,
                    source="invalid",
                    binding_ok=False,
                    issues=[f"COMMANDS_HOME invalid: {e}"],
                    audit_marker=None,
                    audit_event=None,
                )
        else:
            root = self._config_root
            binding_file = root / "commands" / "governance.paths.json"
        
        # Fallback search for common locations if binding file not found
        if not binding_file.exists():
            search_paths = [
                Path.cwd() / "commands" / "governance.paths.json",
                Path.cwd() / ".opencode" / "commands" / "governance.paths.json",
                Path.home() / ".opencode" / "commands" / "governance.paths.json",
            ]
            for search_path in search_paths:
                if search_path.exists():
                    binding_file = search_path
                    break

        python_command = ""

        if not binding_file.exists():
            return BindingEvidence(
                python_command=python_command,
                cmd_profiles={},
                paths={},
                raw_path=None,
                commands_home=None,
                workspaces_home=None,
                config_root=None,
                governance_paths_json=None,
                source="missing",
                binding_ok=False,
                issues=["binding.file.missing"],
                audit_marker=None,
                audit_event=None,
            )

        try:
            payload = json.loads(binding_file.read_text(encoding="utf-8"))
            paths = payload.get("paths") if isinstance(payload, dict) else None
            if not isinstance(paths, dict):
                raise ValueError("paths missing")
            if payload.get("schema") not in _SUPPORTED_BINDING_SCHEMAS:
                raise ValueError("schema invalid")
            commands = normalize_absolute_path(str(paths.get("commandsHome", "")), purpose="paths.commandsHome")
            workspaces = normalize_absolute_path(str(paths.get("workspacesHome", "")), purpose="paths.workspacesHome")
            cmd_profiles = self._parse_command_profiles(payload.get("commandProfiles") if isinstance(payload, dict) else None)
            resolved_paths = {
                "commandsHome": str(commands),
                "workspacesHome": str(workspaces),
            }
            raw_python = paths.get("pythonCommand")
            if not isinstance(raw_python, str) or not raw_python.strip():
                raise ValueError("paths.pythonCommand missing")
            python_command = raw_python.strip()
        except Exception:
            return BindingEvidence(
                python_command=python_command,
                cmd_profiles={},
                paths={},
                raw_path=binding_file,
                commands_home=None,
                workspaces_home=None,
                config_root=None,
                governance_paths_json=binding_file,
                source="invalid",
                binding_ok=False,
                issues=["binding.parse.failed"],
                audit_marker=None,
                audit_event=None,
            )

        issues: list[str] = []
        config_root: Path | None = None

        raw_config_root = paths.get("configRoot")
        if not isinstance(raw_config_root, str) or not raw_config_root.strip():
            issues.append("binding.paths.configRoot.missing")
        else:
            try:
                config_root = normalize_absolute_path(raw_config_root, purpose="paths.configRoot")
            except Exception:
                issues.append("binding.paths.configRoot.invalid")

        binding_ok = len(issues) == 0

        return BindingEvidence(
            python_command=python_command,
            cmd_profiles=cmd_profiles,
            paths=resolved_paths,
            raw_path=binding_file,
            commands_home=commands,
            workspaces_home=workspaces,
            config_root=config_root,
            governance_paths_json=binding_file,
            source="canonical",
            binding_ok=binding_ok,
            issues=issues,
            audit_marker=None,
            audit_event=None,
        )
