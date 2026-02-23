from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .canonical import CanonicalPath


@dataclass(frozen=True)
class BindingEvidence:
    config_root: CanonicalPath
    commands_home: CanonicalPath
    workspaces_home: CanonicalPath
    mode: str
    platform: str
    writes_allowed: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_root": str(self.config_root),
            "commands_home": str(self.commands_home),
            "workspaces_home": str(self.workspaces_home),
            "mode": self.mode,
            "platform": self.platform,
            "writes_allowed": self.writes_allowed,
        }
    
    def validate(self) -> Optional[str]:
        if not self.config_root.path.is_dir():
            return f"Config root does not exist: {self.config_root}"
        
        if not self.commands_home.path.is_dir():
            return f"Commands home does not exist: {self.commands_home}"
        
        if self.workspaces_home.path.is_dir():
            if self.workspaces_home.path == self.config_root.path:
                return "Workspaces home cannot be same as config root"
        
        return None


def load_binding(config_root: Path, mode: str = "user") -> BindingEvidence:
    from .canonical import ensure_absolute_no_traversal
    import platform
    import os
    
    canonical_config = ensure_absolute_no_traversal(config_root)
    commands_home = canonical_config.joinpath("commands")
    workspaces_home = canonical_config.joinpath("workspaces")
    
    writes_allowed = os.environ.get("OPENCODE_FORCE_READ_ONLY", "0") != "1"
    
    return BindingEvidence(
        config_root=canonical_config,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        mode=mode,
        platform=platform.system().lower(),
        writes_allowed=writes_allowed,
    )
