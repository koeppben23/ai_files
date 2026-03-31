from __future__ import annotations

import os
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from governance_runtime.infrastructure.path_contract import (
    PathContractError,
    canonical_config_root,
    normalize_absolute_path,
)


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
    local_root: Path | None
    runtime_home: Path | None
    governance_home: Path | None
    content_home: Path | None
    spec_home: Path | None
    profiles_home: Path | None
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
        env_config_root = os.environ.get("OPENCODE_CONFIG_ROOT")
        if env_config_root:
            configured_root = Path(env_config_root).resolve()
        else:
            configured_root = (config_root if config_root is not None else canonical_config_root()).resolve()
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
                binding_file = root / "governance.paths.json"
                legacy_binding_file = commands_home / "governance.paths.json"
                if not binding_file.exists() and legacy_binding_file.exists():
                    binding_file = legacy_binding_file
                if not binding_file.exists():
                    return BindingEvidence(
                        python_command="",
                        cmd_profiles={},
                        paths={},
                        raw_path=None,
                        commands_home=None,
                        workspaces_home=None,
                        config_root=None,
                        local_root=None,
                        runtime_home=None,
                        governance_home=None,
                        content_home=None,
                        spec_home=None,
                        profiles_home=None,
                        governance_paths_json=None,
                        source="invalid",
                        binding_ok=False,
                        issues=[f"COMMANDS_HOME set but binding file not found: {binding_file}"],
                        audit_marker=None,
                        audit_event=None,
                    )
            except (OSError, ValueError, PathContractError) as e:
                return BindingEvidence(
                    python_command="",
                    cmd_profiles={},
                    paths={},
                    raw_path=None,
                    commands_home=None,
                    workspaces_home=None,
                    config_root=None,
                    local_root=None,
                    runtime_home=None,
                    governance_home=None,
                    content_home=None,
                    spec_home=None,
                    profiles_home=None,
                    governance_paths_json=None,
                    source="invalid",
                    binding_ok=False,
                    issues=[f"COMMANDS_HOME invalid: {e}"],
                    audit_marker=None,
                    audit_event=None,
                )
        else:
            root = self._config_root
            binding_file = root / "governance.paths.json"
            if not binding_file.exists():
                binding_file = root / "commands" / "governance.paths.json"
        
        # Fallback search for common locations if binding file not found
        if not binding_file.exists():
            search_paths = [
                Path.cwd() / "governance.paths.json",
                Path.cwd() / "commands" / "governance.paths.json",
                Path.cwd() / ".opencode" / "governance.paths.json",
                Path.cwd() / ".opencode" / "commands" / "governance.paths.json",
                Path.home() / ".opencode" / "governance.paths.json",
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
                local_root=None,
                runtime_home=None,
                governance_home=None,
                content_home=None,
                spec_home=None,
                profiles_home=None,
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
            config_root = normalize_absolute_path(str(paths.get("configRoot", "")), purpose="paths.configRoot")
            commands = normalize_absolute_path(str(paths.get("commandsHome", "")), purpose="paths.commandsHome")
            workspaces = normalize_absolute_path(str(paths.get("workspacesHome", "")), purpose="paths.workspacesHome")

            raw_local_root = str(paths.get("localRoot", "")).strip()
            if raw_local_root:
                local_root = normalize_absolute_path(raw_local_root, purpose="paths.localRoot")
            elif (commands / "governance").exists() or (commands / "governance_runtime").exists():
                local_root = commands
            else:
                local_root = commands.parent

            def _optional_home(key: str, purpose: str, default: Path) -> Path:
                token = str(paths.get(key, "")).strip()
                if token:
                    return normalize_absolute_path(token, purpose=purpose)
                return default

            runtime_home = _optional_home("runtimeHome", "paths.runtimeHome", local_root / "governance_runtime")
            governance_home = _optional_home("governanceHome", "paths.governanceHome", local_root / "governance")
            content_home = _optional_home("contentHome", "paths.contentHome", local_root / "governance_content")
            spec_home = _optional_home("specHome", "paths.specHome", local_root / "governance_spec")
            profiles_home = _optional_home("profilesHome", "paths.profilesHome", content_home / "profiles")

            cmd_profiles = self._parse_command_profiles(payload.get("commandProfiles") if isinstance(payload, dict) else None)
            resolved_paths = {
                "configRoot": str(config_root),
                "localRoot": str(local_root),
                "commandsHome": str(commands),
                "runtimeHome": str(runtime_home),
                "governanceHome": str(governance_home),
                "contentHome": str(content_home),
                "specHome": str(spec_home),
                "profilesHome": str(profiles_home),
                "workspacesHome": str(workspaces),
            }
            raw_python = paths.get("pythonCommand")
            if not isinstance(raw_python, str) or not raw_python.strip():
                raise ValueError("paths.pythonCommand missing")
            python_command = raw_python.strip()
        except (OSError, ValueError, json.JSONDecodeError, PathContractError):
            return BindingEvidence(
                python_command=python_command,
                cmd_profiles={},
                paths={},
                raw_path=binding_file,
                commands_home=None,
                workspaces_home=None,
                config_root=None,
                local_root=None,
                runtime_home=None,
                governance_home=None,
                content_home=None,
                spec_home=None,
                profiles_home=None,
                governance_paths_json=binding_file,
                source="invalid",
                binding_ok=False,
                issues=["binding.parse.failed"],
                audit_marker=None,
                audit_event=None,
            )

        issues: list[str] = []

        if commands != (config_root / "commands"):
            issues.append("binding.paths.commandsHome.mismatch")
        if workspaces != (config_root / "workspaces"):
            issues.append("binding.paths.workspacesHome.mismatch")
        if runtime_home.parent != local_root:
            issues.append("binding.paths.runtimeHome.parent-mismatch")
        if governance_home.parent != local_root:
            issues.append("binding.paths.governanceHome.parent-mismatch")
        if content_home.parent != local_root:
            issues.append("binding.paths.contentHome.parent-mismatch")
        if spec_home.parent != local_root:
            issues.append("binding.paths.specHome.parent-mismatch")
        if profiles_home.parent != content_home:
            issues.append("binding.paths.profilesHome.parent-mismatch")

        blocking_issues = [
            issue for issue in issues if issue not in {"binding.paths.commandsHome.mismatch", "binding.paths.workspacesHome.mismatch"}
        ]
        binding_ok = len(blocking_issues) == 0

        return BindingEvidence(
            python_command=python_command,
            cmd_profiles=cmd_profiles,
            paths=resolved_paths,
            raw_path=binding_file,
            commands_home=commands,
            workspaces_home=workspaces,
            config_root=config_root,
            local_root=local_root,
            runtime_home=runtime_home,
            governance_home=governance_home,
            content_home=content_home,
            spec_home=spec_home,
            profiles_home=profiles_home,
            governance_paths_json=binding_file,
            source="canonical",
            binding_ok=binding_ok,
            issues=issues,
            audit_marker=None,
            audit_event=None,
        )
