from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from .util import REPO_ROOT


def _load_install_module():
    script = REPO_ROOT / "install.py"
    spec = importlib.util.spec_from_file_location("install_module", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load install.py module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.installer
def test_installer_collectors_exclude_filesystem_metadata(tmp_path: Path):
    """Installer collectors should skip .DS_Store/AppleDouble/__MACOSX metadata."""

    module = _load_install_module()
    source = tmp_path / "source"
    (source / "profiles" / "addons").mkdir(parents=True, exist_ok=True)
    (source / "diagnostics").mkdir(parents=True, exist_ok=True)
    (source / "governance" / "engine").mkdir(parents=True, exist_ok=True)
    (source / "governance" / "__MACOSX").mkdir(parents=True, exist_ok=True)

    # valid files
    (source / "master.md").write_text("# master", encoding="utf-8")
    (source / "profiles" / "rules.backend-python.md").write_text("# profile", encoding="utf-8")
    (source / "profiles" / "addons" / "backendPythonTemplates.addon.yml").write_text(
        "addon_key: backendPythonTemplates\n", encoding="utf-8"
    )
    (source / "diagnostics" / "tool_requirements.json").write_text("{}", encoding="utf-8")
    (source / "governance" / "engine" / "orchestrator.py").write_text("pass\n", encoding="utf-8")

    # metadata garbage that must be excluded
    (source / ".DS_Store").write_text("meta", encoding="utf-8")
    (source / "profiles" / "._rules.backend-python.md").write_text("meta", encoding="utf-8")
    (source / "diagnostics" / ".DS_Store").write_text("meta", encoding="utf-8")
    (source / "governance" / "__MACOSX" / "file.py").write_text("meta", encoding="utf-8")
    (source / "governance" / "engine" / "._orchestrator.py").write_text("meta", encoding="utf-8")

    root_files = module.collect_command_root_files(source)
    profile_files = module.collect_profile_files(source)
    addon_files = module.collect_profile_addon_manifests(source)
    diagnostic_files = module.collect_diagnostics_files(source)
    runtime_files = module.collect_governance_runtime_files(source)

    assert [p.relative_to(source).as_posix() for p in root_files] == ["master.md"]
    assert [p.relative_to(source).as_posix() for p in profile_files] == ["profiles/rules.backend-python.md"]
    assert [p.relative_to(source).as_posix() for p in addon_files] == ["profiles/addons/backendPythonTemplates.addon.yml"]
    assert [p.relative_to(source).as_posix() for p in diagnostic_files] == ["diagnostics/tool_requirements.json"]
    assert [p.relative_to(source).as_posix() for p in runtime_files] == ["governance/engine/orchestrator.py"]
