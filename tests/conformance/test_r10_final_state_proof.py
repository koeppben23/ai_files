"""R10 final state proof: explicit end-state invariants and compatibility surface."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPO_ROOT / "governance"
RUNTIME_ROOT = REPO_ROOT / "governance_runtime"

ALLOWED_ACTIVE_LEGACY_FILES = {
    "governance/addon_catalog.py",
    "governance/application/dto/response_envelope.py",
    "governance/application/ports/clock.py",
    "governance/application/ports/filesystem.py",
    "governance/application/ports/gateways.py",
    "governance/application/ports/git.py",
    "governance/application/ports/logger.py",
    "governance/application/ports/process_runner.py",
    "governance/application/ports/rulebook_source.py",
    "governance/contract.py",
    "governance/contracts/compiler.py",
    "governance/contracts/enforcement.py",
    "governance/contracts/registry.py",
    "governance/contracts/validator.py",
    "governance/domain/access_control.py",
    "governance/domain/audit_contract.py",
    "governance/domain/audit_readout_contract.py",
    "governance/domain/canonical_json.py",
    "governance/domain/classification.py",
    "governance/domain/errors/codes.py",
    "governance/domain/errors/events.py",
    "governance/domain/errors/exceptions.py",
    "governance/domain/evidence_policy.py",
    "governance/domain/failure_model.py",
    "governance/domain/integrity.py",
    "governance/domain/model_identity.py",
    "governance/domain/models/binding.py",
    "governance/domain/models/layouts.py",
    "governance/domain/models/policy_mode.py",
    "governance/domain/models/repo_identity.py",
    "governance/domain/models/rulebooks.py",
    "governance/domain/models/session_state.py",
    "governance/domain/models/write_action.py",
    "governance/domain/operating_profile.py",
    "governance/domain/phase_state_machine.py",
    "governance/domain/policies/gate_policy.py",
    "governance/domain/policies/phase_policy.py",
    "governance/domain/policies/precedence.py",
    "governance/domain/policies/write_policy.py",
    "governance/domain/policy_precedence.py",
    "governance/domain/reason_codes.py",
    "governance/domain/regulated_mode.py",
    "governance/domain/retention.py",
    "governance/enforce.py",
    "governance/entrypoints/bootstrap_backfill.py",
    "governance/entrypoints/bootstrap_binding_evidence.py",
    "governance/entrypoints/bootstrap_executor.py",
    "governance/entrypoints/bootstrap_persistence_hook.py",
    "governance/entrypoints/bootstrap_preflight_readonly.py",
    "governance/entrypoints/bootstrap_session_state.py",
    "governance/entrypoints/bootstrap_session_state_orchestrator.py",
    "governance/entrypoints/bootstrap_session_state_service.py",
    "governance/entrypoints/command_profiles.py",
    "governance/entrypoints/error_handler_bridge.py",
    "governance/entrypoints/error_logs.py",
    "governance/entrypoints/errors/global_handler.py",
    "governance/entrypoints/global_error_handler.py",
    "governance/entrypoints/governed_export_cli.py",
    "governance/entrypoints/human_approval_persist.py",
    "governance/entrypoints/implement_start.py",
    "governance/entrypoints/implementation_decision_persist.py",
    "governance/entrypoints/io/actions.py",
    "governance/entrypoints/io/atomic_write.py",
    "governance/entrypoints/io/fs_verify.py",
    "governance/entrypoints/map_audit_to_canonical.py",
    "governance/entrypoints/md_lint.py",
    "governance/entrypoints/new_work_session.py",
    "governance/entrypoints/persist_workspace_artifacts.py",
    "governance/entrypoints/persist_workspace_artifacts_orchestrator.py",
    "governance/entrypoints/phase4_intake_persist.py",
    "governance/entrypoints/phase5_plan_record_persist.py",
    "governance/entrypoints/reason_registry_selfcheck.py",
    "governance/entrypoints/review_decision_persist.py",
    "governance/entrypoints/review_pr.py",
    "governance/entrypoints/schema_selfcheck.py",
    "governance/entrypoints/session_reader.py",
    "governance/entrypoints/session_state_contract.py",
    "governance/entrypoints/verify_contracts.py",
    "governance/entrypoints/work_session_restore.py",
    "governance/entrypoints/workspace_lock.py",
    "governance/entrypoints/write_policy.py",
    "governance/infrastructure/adapters/filesystem/atomic_write.py",
    "governance/infrastructure/adapters/filesystem/canonical_paths.py",
    "governance/infrastructure/adapters/filesystem/in_memory.py",
    "governance/infrastructure/adapters/filesystem/locks.py",
    "governance/infrastructure/adapters/filesystem/verifier.py",
    "governance/infrastructure/adapters/git/git_cli.py",
    "governance/infrastructure/adapters/logging/event_sink.py",
    "governance/infrastructure/adapters/logging/jsonl_error_sink.py",
    "governance/infrastructure/adapters/process/subprocess_runner.py",
    "governance/infrastructure/adapters/rulebooks/anchor_excerpts.py",
    "governance/infrastructure/adapters/rulebooks/md_loader.py",
    "governance/infrastructure/fs/canonical_paths.py",
    "governance/infrastructure/logging/error_logs.py",
    "governance/infrastructure/logging/global_error_handler.py",
    "governance/installer.py",
    "governance/layers.py",
    "governance/packs/discovery.py",
    "governance/packs/loader_policy.py",
    "governance/packs/pack_service.py",
    "governance/paths/binding.py",
    "governance/paths/canonical.py",
    "governance/paths/layer_adapter.py",
    "governance/paths/layout.py",
    "governance/presentation/renderer.py",
    "governance/receipts/match.py",
    "governance/receipts/store.py",
    "governance/render/delta_renderer.py",
    "governance/render/intent_router.py",
    "governance/render/render_contract.py",
    "governance/render/response_formatter.py",
    "governance/render/token_guard.py",
    "governance/structure.py",
    "governance/verification/behavioral_verifier.py",
    "governance/verification/builder_contract.py",
    "governance/verification/completion_matrix.py",
    "governance/verification/live_flow_verifier.py",
    "governance/verification/pipeline.py",
    "governance/verification/runner.py",
    "governance/verification/static_verifier.py",
    "governance/verification/user_surface_verifier.py",
}


def _runtime_legacy_import_edges() -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    pattern = re.compile(r"^(?:from|import)\s+(governance\.[^\s;]+)", re.MULTILINE)
    for py_file in RUNTIME_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        for m in pattern.finditer(content):
            edges.append((rel, m.group(1)))
    return edges


def _legacy_classification() -> tuple[set[str], set[str], set[str]]:
    runtime_import = re.compile(r"^\s*(?:from|import)\s+governance_runtime\.", re.MULTILINE)
    active_logic = re.compile(r"^\s*(?:def|class)\s+", re.MULTILINE)

    bridge_files: set[str] = set()
    active_files: set[str] = set()
    non_pure_bridges: set[str] = set()

    for py_file in LEGACY_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if runtime_import.search(content):
            bridge_files.add(rel)
            if active_logic.search(content):
                non_pure_bridges.add(rel)
        else:
            active_files.add(rel)

    return bridge_files, active_files, non_pure_bridges


@pytest.mark.conformance
class TestR10FinalStateProof:
    def test_runtime_has_zero_legacy_imports(self) -> None:
        edges = _runtime_legacy_import_edges()
        assert not edges, f"runtime must have zero governance.* imports, found: {edges[:20]}"

    def test_legacy_compatibility_surface_is_explicit_and_stable(self) -> None:
        _, active_files, _ = _legacy_classification()
        assert active_files == ALLOWED_ACTIVE_LEGACY_FILES, (
            "Active compatibility surface drifted. "
            f"unexpected={sorted(active_files - ALLOWED_ACTIVE_LEGACY_FILES)} "
            f"missing={sorted(ALLOWED_ACTIVE_LEGACY_FILES - active_files)}"
        )

    def test_legacy_bridges_are_logic_free(self) -> None:
        _, _, non_pure = _legacy_classification()
        assert not non_pure, f"non-pure legacy bridges remain: {sorted(non_pure)}"

    def test_core_end_state_invariants(self) -> None:
        # Commands surface
        commands = REPO_ROOT / "opencode" / "commands"
        assert commands.is_dir()
        assert len(list(commands.glob("*.md"))) == 8

        # Content/spec/runtime roots
        assert (REPO_ROOT / "governance_content" / "reference" / "master.md").exists()
        assert (REPO_ROOT / "governance_spec" / "phase_api.yaml").exists()
        assert (REPO_ROOT / "governance_runtime" / "VERSION").exists()
        assert (REPO_ROOT / "governance_runtime" / "install" / "install.py").exists()

    def test_version_and_installer_contracts_are_hard(self) -> None:
        canonical_version = (REPO_ROOT / "governance_runtime" / "VERSION").read_text(encoding="utf-8").strip()
        assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", canonical_version)

        for candidate in [REPO_ROOT / "VERSION", REPO_ROOT / "governance" / "VERSION"]:
            if candidate.exists():
                assert candidate.read_text(encoding="utf-8").strip() == canonical_version

        root_install = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        runtime_install = (REPO_ROOT / "governance_runtime" / "install" / "install.py").read_text(encoding="utf-8")
        for token in [
            "import governance_runtime.install.install as _impl",
            "--source-dir",
        ]:
            assert token in root_install
        for token in [
            "GOVERNANCE_PATHS_SCHEMA",
            "def _write_python_binding_file(",
            "OPENCODE_JSON_NAME",
            "PYTHON_BINDING",
            "opencode-governance.paths.v1",
            "def _launcher_template_unix(",
            "def _launcher_template_windows(",
        ]:
            assert token in runtime_install

    def test_workspace_logs_only_write_targets(self) -> None:
        handler = (REPO_ROOT / "governance_runtime" / "infrastructure" / "logging" / "global_error_handler.py").read_text(encoding="utf-8")
        assert "cmd_path / \"logs\"" not in handler

        runtime_installer = (REPO_ROOT / "governance_runtime" / "install" / "install.py").read_text(encoding="utf-8")
        assert "<config_root>/commands/logs" not in runtime_installer

    def test_no_planned_or_tbd_live_contracts(self) -> None:
        contracts_root = REPO_ROOT / "governance_content" / "docs" / "contracts"
        offenders: list[str] = []
        for md in contracts_root.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            if re.search(r"^status:\s*planned\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(md.relative_to(REPO_ROOT).as_posix())
            if re.search(r"^effective_version:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(md.relative_to(REPO_ROOT).as_posix())
            if re.search(r"^conformance_suite:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(md.relative_to(REPO_ROOT).as_posix())
        assert not offenders, f"planned/TBD live contracts remain: {sorted(set(offenders))}"
