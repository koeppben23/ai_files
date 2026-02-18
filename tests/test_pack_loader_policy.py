from __future__ import annotations

import pytest

from governance.packs.loader_policy import validate_pack_artifacts


@pytest.mark.governance
def test_pack_loader_policy_accepts_allowlisted_declarative_files():
    """Allowlisted file types without execution directives should pass."""

    artifacts = {
        "core/pack.yaml": "id: core\nversion: 1.0.0\n",
        "core/rules.md": "# Rules\n- declarative\n",
        "core/readme.txt": "informational text\n",
        "core/template.template": "{{value}}\n",
    }
    violations = validate_pack_artifacts(artifacts)
    assert violations == []


@pytest.mark.governance
def test_pack_loader_policy_rejects_non_allowlisted_file_types():
    """Non-allowlisted file suffixes should fail closed."""

    artifacts = {
        "core/rules.py": "print('nope')\n",
        "core/hook.sh": "echo nope\n",
    }
    violations = validate_pack_artifacts(artifacts)
    assert len(violations) == 2
    assert violations[0].rule == "pack-file-type-allowlist"
    assert violations[1].rule == "pack-file-type-allowlist"


@pytest.mark.governance
def test_pack_loader_policy_rejects_command_lines_yaml_exec_keys_and_shell_fences():
    """Execution-like directives in text artifacts should be rejected."""

    artifacts = {
        "core/rules.md": "!rm -rf /\n",
        "core/pack.yaml": "run: ./danger.sh\n",
        "core/notes.txt": "```bash\necho danger\n```\n",
    }
    violations = validate_pack_artifacts(artifacts)
    rules = [v.rule for v in violations]
    assert "pack-no-command-lines" in rules
    assert "pack-no-exec-yaml-keys" in rules
    assert "pack-no-shell-fences" in rules


@pytest.mark.governance
def test_pack_loader_policy_is_deterministic():
    """Validation output ordering should be deterministic across calls."""

    artifacts = {
        "b/rules.md": "run: a\n",
        "a/rules.md": "!echo x\n",
    }
    first = validate_pack_artifacts(artifacts)
    second = validate_pack_artifacts(artifacts)
    assert first == second
