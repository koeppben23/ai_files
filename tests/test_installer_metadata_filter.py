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
    (source / "scripts").mkdir(parents=True, exist_ok=True)
    (source / "templates" / "github-actions").mkdir(parents=True, exist_ok=True)

    # valid files
    (source / "master.md").write_text("# master", encoding="utf-8")
    (source / "profiles" / "rules.backend-python.md").write_text("# profile", encoding="utf-8")
    (source / "profiles" / "addons" / "backendPythonTemplates.addon.yml").write_text(
        "addon_key: backendPythonTemplates\n", encoding="utf-8"
    )
    (source / "diagnostics" / "tool_requirements.json").write_text("{}", encoding="utf-8")
    (source / "diagnostics" / "CUSTOMER_SCRIPT_CATALOG.json").write_text(
        '{"schema":"governance.customer-script-catalog.v1","scripts":[{"path":"scripts/workflow_template_factory.py","ship_in_release":true}]}\n',
        encoding="utf-8",
    )
    (source / "governance" / "engine" / "orchestrator.py").write_text("pass\n", encoding="utf-8")
    (source / "scripts" / "workflow_template_factory.py").write_text("print('ok')\n", encoding="utf-8")
    (source / "templates" / "github-actions" / "template_catalog.json").write_text(
        '{"schema":"governance.workflow-template-catalog.v1","templates":[{"file":"templates/github-actions/governance-sample.yml"}]}\n',
        encoding="utf-8",
    )
    (source / "templates" / "github-actions" / "governance-sample.yml").write_text("name: Sample\n", encoding="utf-8")

    # metadata garbage that must be excluded
    (source / ".DS_Store").write_text("meta", encoding="utf-8")
    (source / "profiles" / "._rules.backend-python.md").write_text("meta", encoding="utf-8")
    (source / "diagnostics" / ".DS_Store").write_text("meta", encoding="utf-8")
    (source / "governance" / "__MACOSX" / "file.py").write_text("meta", encoding="utf-8")
    (source / "governance" / "engine" / "._orchestrator.py").write_text("meta", encoding="utf-8")
    (source / "scripts" / "._workflow_template_factory.py").write_text("meta", encoding="utf-8")
    (source / "templates" / "github-actions" / ".DS_Store").write_text("meta", encoding="utf-8")

    root_files = module.collect_command_root_files(source)
    profile_files = module.collect_profile_files(source)
    addon_files = module.collect_profile_addon_manifests(source)
    diagnostic_files = module.collect_diagnostics_files(source)
    runtime_files = module.collect_governance_runtime_files(source)
    customer_script_files = module.collect_customer_script_files(source, strict=True)
    workflow_template_files = module.collect_workflow_template_files(source, strict=True)

    assert [p.relative_to(source).as_posix() for p in root_files] == ["master.md"]
    assert [p.relative_to(source).as_posix() for p in profile_files] == ["profiles/rules.backend-python.md"]
    assert [p.relative_to(source).as_posix() for p in addon_files] == ["profiles/addons/backendPythonTemplates.addon.yml"]
    assert [p.relative_to(source).as_posix() for p in diagnostic_files] == [
        "diagnostics/CUSTOMER_SCRIPT_CATALOG.json",
        "diagnostics/tool_requirements.json",
    ]
    assert [p.relative_to(source).as_posix() for p in runtime_files] == ["governance/engine/orchestrator.py"]
    assert [p.relative_to(source).as_posix() for p in customer_script_files] == [
        "scripts/workflow_template_factory.py"
    ]
    assert [p.relative_to(source).as_posix() for p in workflow_template_files] == [
        "templates/github-actions/governance-sample.yml",
        "templates/github-actions/template_catalog.json",
    ]
