from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


_IO_MODULE_PREFIXES = {
    "os",
    "subprocess",
    "shutil",
    "tempfile",
    "pathlib",
}

_PATH_RESOLVE_ALLOWLIST: set[str] = {
    "governance_runtime/infrastructure/binding_evidence_resolver.py",
    "governance_runtime/infrastructure/run_summary_writer.py",
    "governance_runtime/infrastructure/session_pointer.py",
    "governance_runtime/infrastructure/workspace_resolver.py",
    "governance_runtime/entrypoints/session_reader.py",
    "governance_runtime/entrypoints/implement_start.py",
    "governance_runtime/entrypoints/phase5_plan_record_persist.py",
    "governance_runtime/install/install.py",
    "governance_runtime/application/services/phase6_review_orchestrator/orchestrator.py",
}

_APPLICATION_INFRASTRUCTURE_IMPORT_ALLOWLIST: set[str] = {
    "governance_runtime/application/use_cases/audit_readout_builder.py",
    "governance_runtime/application/use_cases/phase5_iterative_review.py",
}

# Side-effect calls allowlist for application layer
# All application→infrastructure side effects must be injected via dependency injection
_SIDE_EFFECT_CALLS_ALLOWLIST: dict[str, set[str]] = {
    # orchestrator.py: Composition-Root reads env for default dependencies
    "governance_runtime/application/services/phase6_review_orchestrator/orchestrator.py": {
        "L84:os.environ",       # Composition-Root: env_reader=lambda key: os.environ.get(key)
        "L264:datetime.now",    # Composition-Root: default clock for load_effective_review_policy
    },
    # llm_caller.py: Composition-Root uses injected env_reader
    "governance_runtime/application/services/phase6_review_orchestrator/llm_caller.py": {
        "L71:subprocess.run",   # Composition-Root: default subprocess runner for LLM execution
    },
    # __init__.py: Composition-Root creates LLMCaller with env_reader
    "governance_runtime/application/services/phase6_review_orchestrator/__init__.py": {
        "L66:os.environ",       # Composition-Root: env_reader for LLMCaller
    },
}


def _iter_python_files(root: Path):
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
    return imported


def _forbidden_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        lineno = getattr(node, "lineno", 0)

        if isinstance(func, ast.Name):
            if func.id == "open":
                mode_arg = None
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                    mode_arg = node.args[1].value
                if "mode" in {kw.arg for kw in node.keywords if kw.arg is not None}:
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                            mode_arg = kw.value.value
                if mode_arg is not None and any(flag in mode_arg for flag in ("w", "a", "x")):
                    violations.append(f"L{lineno}:open_write_mode")

            if func.id == "Path" and any(
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "cwd"
                for arg in node.args
            ):
                violations.append(f"L{lineno}:Path.cwd")

        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
                violations.append(f"L{lineno}:subprocess.{func.attr}")
            if isinstance(func.value, ast.Name) and func.value.id == "datetime" and func.attr in {"now", "utcnow"}:
                violations.append(f"L{lineno}:datetime.{func.attr}")
            if isinstance(func.value, ast.Name) and func.value.id == "Path" and func.attr == "cwd":
                violations.append(f"L{lineno}:Path.cwd")
            if func.attr in {"write_text", "resolve"}:
                violations.append(f"L{lineno}:Path.{func.attr}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr == "environ":
                lineno = getattr(node, "lineno", 0)
                violations.append(f"L{lineno}:os.environ")

    return sorted(set(violations))


def _path_resolve_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "resolve":
            if isinstance(func.value, ast.Name) and func.value.id.endswith("resolver"):
                continue
            lineno = getattr(node, "lineno", 0)
            hits.append(f"L{lineno}:Path.resolve")
    return sorted(set(hits))


@pytest.mark.governance
def test_domain_layer_has_no_direct_io_imports():
    domain_root = REPO_ROOT / "governance_runtime" / "domain"
    for file in _iter_python_files(domain_root):
        imports = _imports(file)
        bad = sorted(
            imp
            for imp in imports
            if any(imp == prefix or imp.startswith(prefix + ".") for prefix in _IO_MODULE_PREFIXES)
        )
        assert not bad, f"domain module imports io/os deps: {file}: {bad}"


@pytest.mark.governance
def test_presentation_layer_does_not_import_infrastructure():
    presentation_root = REPO_ROOT / "governance_runtime" / "presentation"
    forbidden_prefixes = (
        "governance_runtime.infrastructure",
        "governance_runtime.render",
        "governance_runtime.engine",
        "governance_runtime.context",
    )
    for file in _iter_python_files(presentation_root):
        imports = _imports(file)
        bad = sorted(i for i in imports if any(i.startswith(prefix) for prefix in forbidden_prefixes))
        assert not bad, f"presentation imports forbidden layers directly: {file}: {bad}"


@pytest.mark.governance
def test_application_layer_does_not_import_infrastructure():
    application_root = REPO_ROOT / "governance_runtime" / "application"
    for file in _iter_python_files(application_root):
        rel = file.relative_to(REPO_ROOT).as_posix()
        if rel in _APPLICATION_INFRASTRUCTURE_IMPORT_ALLOWLIST:
            continue
        imports = _imports(file)
        bad = sorted(i for i in imports if i.startswith("governance_runtime.infrastructure"))
        assert not bad, f"application imports infrastructure directly: {file}: {bad}"


@pytest.mark.governance
def test_application_layer_does_not_import_legacy_engine_context_layers():
    application_root = REPO_ROOT / "governance_runtime" / "application"
    forbidden_prefixes = (
        "governance_runtime.engine",
        "governance_runtime.context",
        "governance_runtime.persistence",
        "governance_runtime.packs",
        "governance_runtime.render",
        "governance_runtime.presentation",
    )
    for file in _iter_python_files(application_root):
        imports = _imports(file)
        bad = sorted(i for i in imports if any(i.startswith(prefix) for prefix in forbidden_prefixes))
        assert not bad, f"application imports forbidden legacy layers: {file}: {bad}"


@pytest.mark.governance
def test_render_and_presentation_do_not_import_engine_context_or_infrastructure():
    roots = [REPO_ROOT / "governance_runtime" / "render", REPO_ROOT / "governance_runtime" / "presentation"]
    forbidden_prefixes = (
        "governance_runtime.engine",
        "governance_runtime.context",
        "governance_runtime.infrastructure",
    )
    for root in roots:
        for file in _iter_python_files(root):
            imports = _imports(file)
            bad = sorted(i for i in imports if any(i.startswith(prefix) for prefix in forbidden_prefixes))
            assert not bad, f"presentation/render imports forbidden layers: {file}: {bad}"


@pytest.mark.governance
def test_domain_and_application_layers_forbid_side_effect_calls():
    roots = [REPO_ROOT / "governance_runtime" / "domain", REPO_ROOT / "governance_runtime" / "application"]
    violations: list[str] = []
    for root in roots:
        for file in _iter_python_files(root):
            rel = file.relative_to(REPO_ROOT).as_posix()
            allowed_calls = _SIDE_EFFECT_CALLS_ALLOWLIST.get(rel, set())
            bad_calls = _forbidden_calls(file)
            # Filter out allowed calls
            filtered_calls = [call for call in bad_calls if call not in allowed_calls]
            if filtered_calls:
                violations.append(f"{file}: {filtered_calls}")

    assert not violations, "forbidden side-effect calls detected in domain/application:\n" + "\n".join(violations)


@pytest.mark.governance
def test_governance_path_resolve_calls_are_allowlisted():
    governance_root = REPO_ROOT / "governance_runtime"
    violations: list[str] = []
    for file in _iter_python_files(governance_root):
        rel = file.relative_to(REPO_ROOT).as_posix()
        if rel in _PATH_RESOLVE_ALLOWLIST:
            continue
        hits = _path_resolve_calls(file)
        if hits:
            violations.append(f"{file}: {hits}")

    assert not violations, "Path.resolve usage must be explicitly allowlisted:\n" + "\n".join(violations)


@pytest.mark.governance
def test_bootstrap_persistence_does_not_import_entrypoints():
    module = REPO_ROOT / "bootstrap" / "persistence.py"
    imports = _imports(module)
    bad = sorted(imp for imp in imports if imp.startswith("governance_runtime.entrypoints"))
    assert not bad, f"bootstrap persistence must not import entrypoint modules: {bad}"


# Files allowed to do alias resolution
# state_normalizer.py is the PRIMARY location for alias resolution
# Other files are temporary - to be removed as migration progresses (Sprint E Phase 3+)
_ALIAS_RESOLUTION_ALLOWLIST: set[str] = {
    # PRIMARY: State normalizer (all alias resolution happens here)
    "governance_runtime/application/services/state_normalizer.py",
    # MIGRATED: Now use normalize_to_canonical() for reads
    "governance_runtime/application/services/phase6_review_orchestrator/orchestrator.py",
    "governance_runtime/application/services/phase5_normalizer.py",
    "governance_runtime/application/services/state_accessor.py",
    "governance_runtime/application/services/phase6_review_orchestrator/policy_resolver.py",
    "governance_runtime/application/services/transition_model.py",
    # SCHEMA: Runtime schema validation (reads phase aliases for validation)
    "governance_runtime/application/services/state_document_validator.py",
    # LEGACY COMPATIBILITY: To be migrated later
    "governance_runtime/entrypoints/session_reader.py",
    # ENTRYPOINTS: To be migrated later
    "governance_runtime/entrypoints/work_session_restore.py",
    "governance_runtime/entrypoints/review_decision_persist.py",
    "governance_runtime/entrypoints/implementation_decision_persist.py",
    "governance_runtime/entrypoints/implement_start.py",
    "governance_runtime/entrypoints/phase5_plan_record_persist.py",
    "governance_runtime/entrypoints/phase4_intake_persist.py",
    "governance_runtime/entrypoints/new_work_session.py",
    "governance_runtime/entrypoints/bootstrap_preflight_readonly.py",
    "governance_runtime/entrypoints/bootstrap_persistence_hook.py",
    "governance_runtime/entrypoints/persist_workspace_artifacts_orchestrator.py",
    # ENGINE: To be migrated later
    "governance_runtime/engine/session_state_invariants.py",
    "governance_runtime/kernel/phase_kernel.py",
    # INFRASTRUCTURE: To be migrated later
    "governance_runtime/infrastructure/work_run_archive.py",
    "governance_runtime/infrastructure/run_audit_artifacts.py",
    "governance_runtime/infrastructure/rendering/snapshot_renderer.py",
    "governance_runtime/infrastructure/logging/global_error_handler.py",
    "governance_runtime/infrastructure/io_verify.py",
    # OTHER: Uses canonical/alias access patterns
    "governance_runtime/application/dto/phase_next_action_contract.py",
    "governance_runtime/render/response_formatter.py",
    "governance_runtime/cli/bootstrap_executor.py",
    "governance_runtime/application/use_cases/bootstrap_persistence.py",
    "governance_runtime/application/use_cases/session_state_helpers.py",
    "governance_runtime/session_state/transitions.py",
    "governance_runtime/application/services/state_invariants.py",
}


def _find_alias_resolution_calls(file: Path) -> list[str]:
    """Find legacy field alias patterns like .get("Phase") or .get("phase")."""
    content = file.read_text(encoding="utf-8")
    lines = content.split("\n")
    hits = []

    # Pattern: .get("Phase") or .get("phase") or .get("Next") or .get("next")
    # These are legacy alias patterns that should only be in state_normalizer.py
    alias_patterns = [
        '.get("Phase")',
        '.get("phase")',  # This is OK as canonical, but flag for review
        '.get("Next")',
        '.get("next")',
        '.get("WorkflowComplete")',
        '.get("workflow_complete")',
        '.get("Phase5State")',
        '.get("phase5_state")',
        '.get("PlanRecordStatus")',
        '.get("plan_record_status")',
        '.get("LoadedRulebooks")',
        '.get("loaded_rulebooks")',
        '.get("AddonsEvidence")',
        '.get("addons_evidence")',
        '.get("ActiveProfile")',
        '.get("active_profile")',
        '.get("Kernel")',
        '.get("kernel")',
        '.get("RepoFingerprint")',
        '.get("repo_fingerprint")',
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue
        # Skip kwargs.get() patterns (function parameters, not session state)
        if "kwargs.get(" in line or "**kwargs" in stripped:
            continue
        for pattern in alias_patterns:
            if pattern in line:
                hits.append(f"L{i}:{pattern}")

    return hits


@pytest.mark.governance
def test_alias_resolution_only_in_allowed_modules():
    """Alias resolution (.get('Phase') etc.) only allowed in state_normalizer.py and legacy modules."""
    governance_root = REPO_ROOT / "governance_runtime"
    violations = []

    for file in _iter_python_files(governance_root):
        rel = file.relative_to(REPO_ROOT).as_posix()
        if rel in _ALIAS_RESOLUTION_ALLOWLIST:
            continue
        hits = _find_alias_resolution_calls(file)
        if hits:
            violations.append(f"{file}: {hits}")

    assert not violations, (
        "Legacy alias resolution (.get('Phase'), .get('Next') etc.) must only happen in:\n"
        "- state_normalizer.py (primary)\n"
        "- legacy_compat.py (backward compatibility)\n"
        "- Violations found:\n" + "\n".join(violations)
    )
