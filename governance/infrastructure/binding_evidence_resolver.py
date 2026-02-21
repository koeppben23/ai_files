from __future__ import annotations

from dataclasses import dataclass
import json
import os
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
    commands_home: Path
    workspaces_home: Path
    config_root: Path | None
    governance_paths_json: Path | None
    source: Literal["canonical", "trusted_override", "dev_cwd_search", "missing", "invalid"]
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
        self._env = env if env is not None else os.environ
        configured_root = config_root if config_root is not None else canonical_config_root()
        self._config_root = normalize_absolute_path(str(configured_root), purpose="resolver.config_root")
        self._cwd_provider = cwd_provider if cwd_provider is not None else Path.cwd

    def _allow_cwd_search(self, *, mode: str, host_caps: Any | None) -> bool:
        if str(mode).strip().lower() == "pipeline":
            return False
        if str(self._env.get("OPENCODE_ALLOW_CWD_BINDINGS", "")).strip() != "1":
            return False
        if host_caps is None:
            return False
        writable = bool(getattr(host_caps, "fs_write_commands_home", False))
        readable = bool(getattr(host_caps, "fs_read_commands_home", False))
        return writable or readable

    @staticmethod
    def _normalize_path(path: Path) -> Path:
        if not path.is_absolute():
            raise ValueError("binding candidate path must be absolute")
        return Path(os.path.normpath(os.path.abspath(str(path))))

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
        if self._allow_cwd_search(mode=mode, host_caps=host_caps):
            cwd = self._normalize_path(self._cwd_provider())
            candidates.extend(
                (parent / "commands" / "governance.paths.json", "dev_cwd_search")
                for parent in (cwd, *cwd.parents)
            )
        return candidates

    def resolve(self, *, mode: str = "user", host_caps: Any | None = None) -> BindingEvidence:
        root = self._config_root
        commands_home = root / "commands"
        workspaces_home = root / "workspaces"
        python_command = ""

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
                commands_home=commands_home,
                workspaces_home=workspaces_home,
                config_root=None,
                governance_paths_json=binding_file,
                source="invalid",
                binding_ok=False,
                issues=["binding.parse.failed"],
                audit_marker=None,
                audit_event=None,
            )

        audit_marker = "POLICY_PRECEDENCE_APPLIED" if binding_source != "canonical" else None
        audit_event: dict[str, object] | None = None
        if audit_marker is not None:
            audit_event = {
                "event": audit_marker,
                "source": binding_source,
                "candidate_path": str(binding_file),
                "mode": str(mode).strip().lower() or "user",
                "flags": {
                    "allow_trusted_binding_override": str(
                        self._env.get("OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE", "")
                    ).strip()
                    == "1",
                    "allow_cwd_bindings": str(self._env.get("OPENCODE_ALLOW_CWD_BINDINGS", "")).strip() == "1",
                },
            }

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

        if config_root is not None and commands != config_root / "commands":
            issues.append("binding.paths.commandsHome.not_under_configRoot")
        if config_root is not None and workspaces != config_root / "workspaces":
            issues.append("binding.paths.workspacesHome.not_under_configRoot")

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
            source=binding_source,
            binding_ok=binding_ok,
            issues=issues,
            audit_marker=audit_marker,
            audit_event=audit_event,
        )
