from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Literal, Mapping

from governance.infrastructure.path_contract import canonical_config_root, normalize_absolute_path


@dataclass(frozen=True)
class BindingEvidence:
    commands_home: Path
    workspaces_home: Path
    governance_paths_json: Path | None
    source: Literal["canonical", "dev_cwd_search", "missing", "invalid"]
    binding_ok: bool


class BindingEvidenceResolver:
    def __init__(self, *, env: Mapping[str, str] | None = None, config_root: Path | None = None):
        self._env = env if env is not None else os.environ
        self._config_root = config_root if config_root is not None else canonical_config_root()

    def _allow_cwd_search(self) -> bool:
        return str(self._env.get("OPENCODE_ALLOW_CWD_BINDINGS", "")).strip() == "1"

    def _candidates(self) -> list[Path]:
        root = self._config_root
        candidates = [root / "commands" / "governance.paths.json"]
        if self._allow_cwd_search():
            cwd = Path.cwd().resolve()
            candidates.extend(parent / "commands" / "governance.paths.json" for parent in (cwd, *cwd.parents))
        return candidates

    def resolve(self) -> BindingEvidence:
        root = self._config_root
        commands_home = root / "commands"
        workspaces_home = root / "workspaces"

        binding_file: Path | None = None
        for candidate in self._candidates():
            resolved = candidate.expanduser().resolve()
            if resolved.exists():
                binding_file = resolved
                break

        if binding_file is None:
            return BindingEvidence(
                commands_home=commands_home,
                workspaces_home=workspaces_home,
                governance_paths_json=None,
                source="missing",
                binding_ok=False,
            )

        try:
            payload = json.loads(binding_file.read_text(encoding="utf-8"))
            paths = payload.get("paths") if isinstance(payload, dict) else None
            if not isinstance(paths, dict):
                raise ValueError("paths missing")
            commands = normalize_absolute_path(str(paths.get("commandsHome", "")), purpose="paths.commandsHome")
            workspaces = normalize_absolute_path(str(paths.get("workspacesHome", "")), purpose="paths.workspacesHome")
        except Exception:
            return BindingEvidence(
                commands_home=commands_home,
                workspaces_home=workspaces_home,
                governance_paths_json=binding_file,
                source="invalid",
                binding_ok=False,
            )

        return BindingEvidence(
            commands_home=commands,
            workspaces_home=workspaces,
            governance_paths_json=binding_file,
            source="dev_cwd_search" if self._allow_cwd_search() else "canonical",
            binding_ok=True,
        )
