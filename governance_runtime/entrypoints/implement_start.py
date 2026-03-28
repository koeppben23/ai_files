#!/usr/bin/env python3
"""Implementation execution rail -- ``/implement`` entrypoint.

This entrypoint is an executor orchestrator plus validator. It does not edit
domain files directly.

Allowed local writes from this entrypoint are limited to governance/session
diagnostics (for example ``.governance/implementation/*``, session state, and
events). Domain/source changes must come from the external LLM executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.application.services.state_accessor import get_active_gate, get_phase
from governance_runtime.contracts.enforcement import require_complete_contracts
from governance_runtime.engine.implementation_validation import (
    CheckResult,
    ExecutorRunResult,
    RC_CHECK_COLLECTION_FAILED,
    RC_CHECK_RUNNER_FAILED,
    RC_CHECK_SELECTOR_INVALID,
    RC_EXECUTOR_FAILED,
    RC_EXECUTOR_NOT_CONFIGURED,
    RC_TARGETED_CHECKS_MISSING,
    build_plan_coverage,
    split_domain_changed_files,
    to_report_payload,
    validate_implementation,
    write_validation_report,
)
from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.fs_atomic import atomic_write_text
from governance_runtime.infrastructure.governance_context_materializer import (
    GovernanceContextMaterializationError,
    materialize_governance_artifacts,
    validate_materialized_artifacts,
)
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.opencode_model_binding import (
    has_active_desktop_llm_binding as _has_desktop_llm_binding,
    resolve_active_opencode_model,
)
from governance_runtime.infrastructure.governance_binding_resolver import (
    GovernanceBindingResolutionError,
    resolve_governance_binding,
)
from governance_runtime.infrastructure.governance_config_loader import get_pipeline_mode
from governance_runtime.infrastructure.plan_record_state import resolve_plan_record_signal
from governance_runtime.infrastructure.workspace_paths import governance_runtime_state_dir
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso
from governance_runtime.application.services.state_normalizer import normalize_to_canonical


def _resolve_active_session_path() -> tuple[Path, Path]:
    session_path, _, _, workspace_dir = resolve_active_session_paths()
    events_path = workspace_dir / "logs" / "events.jsonl"
    return session_path, events_path


BLOCKED_IMPLEMENT_START_INVALID = "BLOCKED-UNSPECIFIED"
BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE = "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"
BLOCKED_MANDATE_SCHEMA_UNAVAILABLE = "MANDATE-SCHEMA-UNAVAILABLE"

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


@lru_cache(maxsize=1)
def _load_mandates_schema() -> dict[str, object] | None:
    """Load the compiled governance mandates schema (JSON). Returns None if unavailable."""
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_effective_authoring_policy_text(
    state: Mapping[str, object],
    commands_home: Path,
) -> tuple[str, str]:
    """Load and format effective authoring policy for LLM injection.

    Returns (policy_text, error_code). error_code is empty on success.
    Fail-closed: returns error_code if policy cannot be built.
    """
    from governance_runtime.application.use_cases.build_effective_llm_policy import (
        BLOCKED_EFFECTIVE_POLICY_EMPTY,
        BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID,
        BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED,
        BLOCKED_RULEBOOK_CONTENT_UNLOADABLE,
        EffectivePolicyInput,
        build_effective_llm_policy,
        format_authoring_policy_for_llm,
    )

    lrb: dict[str, object] = {}
    addons_ev: dict[str, object] = {}
    active_profile = "profile.fallback-minimum"

    state_obj = state
    if isinstance(state, dict):
        nested = state.get("SESSION_STATE")
        if isinstance(nested, dict):
            state_obj = nested
    if isinstance(state_obj, dict):
        lrb_raw = state_obj.get("LoadedRulebooks")
        if isinstance(lrb_raw, dict):
            lrb = lrb_raw
        addons_ev_raw = state_obj.get("AddonsEvidence")
        if isinstance(addons_ev_raw, dict):
            addons_ev = addons_ev_raw
        active_profile = str(
            state_obj.get("ActiveProfile")
            or state_obj.get("active_profile")
            or "profile.fallback-minimum"
        ).strip()

    if not lrb:
        return "", BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE

    schema_path = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "schemas"
        / "effective_llm_policy.v1.schema.json"
    )
    compiled_at = _now_iso()

    try:
        input_data = EffectivePolicyInput(
            active_profile=active_profile,
            loaded_rulebooks=lrb,
            addons_evidence=addons_ev,
            commands_home=commands_home,
            schema_path=schema_path,
            compiled_at=compiled_at,
        )
        result = build_effective_llm_policy(input_data)
        policy_text = format_authoring_policy_for_llm(result.policy.authoring_policy)
        return policy_text, ""
    except (
        BLOCKED_RULEBOOK_CONTENT_UNLOADABLE,
        BLOCKED_RULEBOOK_CONTENT_PARSE_FAILED,
        BLOCKED_EFFECTIVE_POLICY_EMPTY,
        BLOCKED_EFFECTIVE_POLICY_SCHEMA_INVALID,
    ):
        return "", BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE
    except Exception:
        return "", BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE


def _build_authoring_mandate_text(schema: dict[str, object]) -> str:
    """Build a plain-text authoring mandate from the compiled JSON schema."""
    dm = schema.get("developer_mandate", {})
    if not isinstance(dm, dict):
        return ""

    lines: list[str] = []

    role = str(dm.get("role", "")).strip()
    if role:
        lines.append(f"Role: {role}")

    posture = dm.get("core_posture", [])
    if posture:
        for item in posture:
            lines.append(f"- {item}")

    evidence = dm.get("evidence_rule", [])
    if evidence:
        lines.append("Evidence rule:")
        for item in evidence:
            lines.append(f"- {item}")

    objectives = dm.get("primary_authoring_objectives", [])
    if objectives:
        lines.append("Authoring objectives:")
        for item in objectives:
            lines.append(f"- {item}")

    lenses = dm.get("authoring_lenses", [])
    if lenses:
        lines.append("Authoring lenses:")
        for idx, lens in enumerate(lenses, 1):
            if isinstance(lens, dict):
                name = lens.get("name", "")
                body = lens.get("body", [])
                ask = lens.get("ask", [])
                lines.append(f"{idx}. {name}")
                for b in body:
                    lines.append(f"- {b}")
                for a in ask:
                    lines.append(f"  Ask: {a}")

    method = dm.get("authoring_method", [])
    if method:
        lines.append("Authoring method:")
        for item in method:
            lines.append(f"- {item}")

    contract = dm.get("output_contract", {})
    if contract:
        lines.append("Output contract:")
        if isinstance(contract, dict):
            for key, desc in contract.items():
                lines.append(f"- {key}: {desc}")

    decision = dm.get("decision_rules", [])
    if decision:
        lines.append("Decision rules:")
        for item in decision:
            lines.append(f"- {item}")

    addendum = dm.get("governance_addendum", [])
    if addendum:
        lines.append("Governance addendum:")
        for item in addendum:
            lines.append(f"- {item}")

    return "\n".join(lines)


@lru_cache(maxsize=1)
def _get_developer_output_schema_text() -> str:
    """Extract developerOutputSchema from compiled mandates schema as JSON text."""
    schema = _load_mandates_schema()
    if schema:
        try:
            defs = schema.get("$defs", {})
            for key in defs:
                if key == "developerOutputSchema":
                    return json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", **defs[key]}, indent=2)
        except Exception:
            pass
    return ""




def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, text)


def _append_event(path: Path, event: dict[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl_event(path, event, append=True)
        return True
    except Exception:
        return False


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def _latest_plan_text(plan_record_file: Path, state: Mapping[str, object] | None = None) -> str:
    if not plan_record_file.exists():
        payload = {}
    else:
        payload = _load_json(plan_record_file)

    versions = payload.get("versions") if isinstance(payload, Mapping) else None
    if isinstance(versions, list) and versions:
        latest = versions[-1] if isinstance(versions[-1], dict) else {}
        if isinstance(latest, dict):
            plan_text = str(latest.get("plan_record_text") or "").strip()
            if plan_text:
                return plan_text

    canonical_state = normalize_to_canonical(dict(state or {}))
    review_pkg = canonical_state.get("review_package")
    if isinstance(review_pkg, Mapping):
        plan_body = str(review_pkg.get("plan_body") or "").strip()
        if plan_body:
            return plan_body
        approved_plan_summary = str(review_pkg.get("approved_plan_summary") or "").strip()
        if approved_plan_summary:
            return approved_plan_summary

    plan_digest = str(canonical_state.get("phase5_plan_record_digest") or "").strip()
    if plan_digest:
        return plan_digest

    return ""


def _contracts_path(session_path: Path, state: Mapping[str, object]) -> Path:
    explicit = str(state.get("requirement_contracts_source") or "").strip()
    if explicit:
        candidate = Path(explicit)
        if candidate.is_absolute():
            return candidate
        return session_path.parent / explicit
    return session_path.parent / ".governance" / "contracts" / "compiled_requirements.json"


def _load_compiled_requirements(session_path: Path, state: Mapping[str, object]) -> list[dict[str, object]]:
    path = _contracts_path(session_path, state)
    if not path.exists() or not path.is_file():
        return []
    try:
        payload = _load_json(path)
    except Exception:
        return []
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        return []
    out: list[dict[str, object]] = []
    for item in requirements:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def _load_compiled_requirements_source_authority(session_path: Path, state: Mapping[str, object]) -> str:
    path = _contracts_path(session_path, state)
    if not path.exists() or not path.is_file():
        return ""
    try:
        payload = _load_json(path)
    except Exception:
        return ""
    return str(payload.get("source_authority") or "").strip()


def _allow_legacy_requirement_source() -> bool:
    token = str(os.environ.get("GOVERNANCE_ALLOW_LEGACY_MARKDOWN_REQUIREMENTS") or "").strip().lower()
    return token in {"1", "true", "yes", "on"}


def _extract_hotspot_files(requirements: list[dict[str, object]]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        hotspots = requirement.get("code_hotspots")
        if not isinstance(hotspots, list):
            continue
        for hotspot in hotspots:
            token = str(hotspot or "").strip().replace("\\", "/")
            if not token or token.startswith(".."):
                continue
            if token in seen:
                continue
            seen.add(token)
            files.append(token)
    return files


def _repo_root(session_path: Path, state: Mapping[str, object]) -> Path:
    explicit = str(state.get("RepoRoot") or state.get("repo_root") or "").strip()
    if explicit:
        root = Path(explicit)
        if root.is_absolute() and root.exists() and root.is_dir():
            return root
    if session_path.parent.exists() and session_path.parent.is_dir() and (session_path.parent / ".git").exists():
        return session_path.parent

    identity_map = session_path.parent / "repo-identity-map.yaml"
    if identity_map.exists() and identity_map.is_file():
        try:
            payload = _load_json(identity_map)
            mapped_root = Path(str(payload.get("repoRoot") or "").strip())
            if mapped_root.is_absolute() and mapped_root.exists() and mapped_root.is_dir():
                return mapped_root
        except Exception:
            pass

    if session_path.parent.exists() and session_path.parent.is_dir():
        return session_path.parent
    cwd = Path(os.path.abspath(str(Path.cwd())))
    if (cwd / ".git").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent
    return session_path.parent


def _parse_changed_files_from_git_status(repo_root: Path) -> list[str]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if probe.returncode != 0:
        return []
    changed_files: list[str] = []
    for raw in str(probe.stdout or "").splitlines():
        if len(raw) < 4:
            continue
        changed_files.append(raw[3:].strip().replace("\\", "/"))
    return sorted(set(changed_files))


def _capture_repo_change_baseline(repo_root: Path) -> dict[str, object]:
    try:
        probe = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {
            "repo_dirty_before": False,
            "tracked_changes_before": [],
            "untracked_before": [],
        }
    if probe.returncode != 0:
        return {
            "repo_dirty_before": False,
            "tracked_changes_before": [],
            "untracked_before": [],
        }
    tracked: list[str] = []
    untracked: list[str] = []
    for raw in str(probe.stdout or "").splitlines():
        if len(raw) < 4:
            continue
        status = raw[:2]
        path = raw[3:].strip().replace("\\", "/")
        if not path:
            continue
        if status == "??":
            untracked.append(path)
        else:
            tracked.append(path)
    tracked = sorted(set(tracked))
    untracked = sorted(set(untracked))
    return {
        "repo_dirty_before": bool(tracked or untracked),
        "tracked_changes_before": tracked,
        "untracked_before": untracked,
    }


def _classify_check_failure_kind(exit_code: int | None, output: str) -> str | None:
    code = int(exit_code or 0)
    lower = str(output or "").lower()
    if code == 0:
        return None
    if code == 4:
        if "no tests ran" in lower or "not found" in lower or "collected 0 items" in lower:
            return "selector_invalid"
        return "collection_failed"
    return "runner_failed"


def _selector_target_exists(repo_root: Path, selector: str) -> bool:
    token = str(selector or "").strip()
    if not token:
        return False
    if token.startswith("-"):
        return False
    target = token.split("::", 1)[0].strip()
    if not target:
        return False
    normalized = target.replace("\\", "/")
    if normalized.startswith("../"):
        return False
    path = repo_root / normalized
    return path.exists()


def _derive_targeted_check_fallbacks(repo_root: Path, requirements: list[dict[str, object]]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        hotspots = requirement.get("code_hotspots")
        if not isinstance(hotspots, list):
            continue
        for hotspot in hotspots:
            rel = str(hotspot or "").strip().replace("\\", "/")
            if not rel or rel.startswith("../"):
                continue
            stem = Path(rel).stem
            if not stem:
                continue
            for candidate in (f"tests/test_{stem}.py", f"tests/{stem}_test.py"):
                if candidate in seen:
                    continue
                if (repo_root / candidate).exists():
                    seen.add(candidate)
                    candidates.append(candidate)
    if candidates:
        return candidates
    if (repo_root / "tests").exists():
        return ["tests"]
    return []


def _parse_json_events_to_text(response_text: str) -> str:
    """Parse OpenCode JSON events and extract assistant text response.

    When --format json is used, opencode run returns NDJSON events.
    We only accept 'text' type events as the assistant response payload.

    Args:
        response_text: Raw stdout from opencode run --format json

    Returns:
        Extracted text content from assistant response, or original text if parsing fails.
    """
    if not response_text.strip():
        return response_text

    try:
        lines = response_text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "text":
                continue
            part = event.get("part", {})
            text_content = part.get("text", "")
            if text_content:
                return text_content
    except Exception:
        pass

    return response_text


def _build_executor_env(*, bridge_mode: bool) -> dict[str, str] | None:
    if not bridge_mode:
        return None
    env = dict(os.environ)
    for key in (
        "OPENCODE",
        "OPENCODE_CLIENT",
        "OPENCODE_PID",
        "OPENCODE_SERVER_USERNAME",
        "OPENCODE_SERVER_PASSWORD",
    ):
        env.pop(key, None)
    return env


def _resolve_active_opencode_session_id() -> str:
    session_id = str(os.environ.get("OPENCODE_SESSION_ID") or "").strip()
    if session_id:
        return session_id
    model_info = resolve_active_opencode_model()
    if not isinstance(model_info, dict):
        return ""
    return str(model_info.get("session_id") or "").strip()


def _bridge_timeout_seconds() -> int:
    raw = str(os.environ.get("AI_GOVERNANCE_BRIDGE_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return 120
    try:
        value = int(raw)
    except ValueError:
        return 120
    return max(30, min(value, 600))


def _file_sha256(path: Path) -> str:
    try:
        data = path.read_bytes()
    except Exception:
        return ""
    return hashlib.sha256(data).hexdigest()


def _capture_hotspot_hashes(repo_root: Path, hotspots: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in hotspots:
        rel = str(token or "").strip().replace("\\", "/")
        if not rel or rel.startswith(".."):
            continue
        out[rel] = _file_sha256(repo_root / rel)
    return out


def _has_active_desktop_llm_binding() -> bool:
    if str(os.environ.get("OPENCODE") or "").strip() == "1":
        return True
    return _has_desktop_llm_binding()


def _resolve_desktop_executor_bridge_cmd(*, repo_root: Path) -> str:
    candidate_env = str(os.environ.get("OPENCODE_CLI_BIN") or "").strip()
    candidate_paths: list[str] = []
    if candidate_env:
        candidate_paths.append(candidate_env)
    candidate_paths.append("/Applications/OpenCode.app/Contents/MacOS/opencode-cli")
    which_opencode = shutil.which("opencode")
    if which_opencode:
        candidate_paths.append(which_opencode)
    which_opencode_cli = shutil.which("opencode-cli")
    if which_opencode_cli:
        candidate_paths.append(which_opencode_cli)

    cli_bin = ""
    for token in candidate_paths:
        path = Path(token)
        if path.exists() and os.access(str(path), os.X_OK):
            cli_bin = str(path)
            break
    if not cli_bin:
        return ""

    session_id = _resolve_active_opencode_session_id()
    if not session_id:
        return ""

    model_info = resolve_active_opencode_model()
    model_token = ""
    if isinstance(model_info, dict):
        provider = str(model_info.get("provider") or "").strip()
        model_id = str(model_info.get("model_id") or "").strip()
        if provider and model_id:
            model_token = f"{provider}/{model_id}"

    message = (
        "Read the attached implementation context JSON and execute the approved plan by editing "
        "domain repository files (not .governance). Return strict JSON only."
    )
    cmd_parts = [
        shlex.quote(cli_bin),
        "run",
        "--session",
        shlex.quote(session_id),
        "--format",
        "json",
        "--file",
        "{context_file}",
    ]
    if model_token:
        cmd_parts.extend(["--model", shlex.quote(model_token)])
    cmd_parts.append(shlex.quote(message))
    return " ".join(cmd_parts)


def _run_llm_edit_step(
    *,
    repo_root: Path,
    state: Mapping[str, object],
    ticket_text: str,
    task_text: str,
    plan_text: str,
    required_hotspots: list[str],
    commands_home: Path | None = None,
    config_root: Path | None = None,
    workspaces_home: Path | None = None,
    repo_fingerprint: str | None = None,
    pipeline_mode: bool = False,
    execution_binding: str = "",
) -> dict[str, object]:
    executor_cmd = execution_binding if pipeline_mode else ""
    has_executor = bool(executor_cmd) if pipeline_mode else _has_active_desktop_llm_binding()
    implementation_dir = repo_root / ".governance" / "implementation"
    implementation_dir.mkdir(parents=True, exist_ok=True)
    context_file = implementation_dir / "llm_edit_context.json"
    stdout_file = implementation_dir / "executor_stdout.log"
    stderr_file = implementation_dir / "executor_stderr.log"

    resolved_workspaces_home = workspaces_home
    resolved_repo_fingerprint = str(repo_fingerprint or "").strip()
    if resolved_workspaces_home is None or not resolved_repo_fingerprint:
        scope_root = config_root or (repo_root / ".governance")
        resolved_workspaces_home = scope_root / "workspaces"
        candidate = str(repo_root.name or "").strip()
        if re.fullmatch(r"[0-9a-f]{24}", candidate):
            resolved_repo_fingerprint = candidate
        else:
            resolved_repo_fingerprint = hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:24]

    governance_root = resolved_workspaces_home
    runtime_state_dir = governance_runtime_state_dir(resolved_workspaces_home, resolved_repo_fingerprint)
    runtime_state_dir.mkdir(parents=True, exist_ok=True)

    mandate_text = ""
    schema = _load_mandates_schema()
    if schema:
        mandate_text = _build_authoring_mandate_text(schema)
    else:
        return {
            "blocked": True,
            "reason": "mandate-schema-unavailable",
            "reason_code": BLOCKED_MANDATE_SCHEMA_UNAVAILABLE,
            "recovery_action": "Provide governance_mandates.v1.schema.json at the canonical runtime location.",
            "binding_resolved": has_executor,
            "invoke_backend_available": has_executor,
            "message": "Required mandate schema governance_mandates.v1.schema.json is unavailable.",
        }

    effective_policy_text, effective_policy_error = "", ""
    if commands_home is not None:
        effective_policy_text, effective_policy_error = _load_effective_authoring_policy_text(
            state=state,
            commands_home=commands_home,
        )
    # Determine if we have an execution binding for active mode.
    # Direct mode: active chat binding is authoritative.
    # Pipeline mode: explicit execution binding is authoritative.
    if has_executor and effective_policy_error:
        return {
            "blocked": True,
            "reason": "effective-policy-unavailable",
            "reason_code": BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            "recovery_action": "Ensure rulebooks and addons are loadable and contain valid policy content.",
            "binding_resolved": has_executor,
            "invoke_backend_available": has_executor,
        }

    try:
        materialization = materialize_governance_artifacts(
            output_dir=runtime_state_dir,
            config_root=governance_root,
            plan_mandate=mandate_text if mandate_text else None,
            effective_policy=effective_policy_text if effective_policy_text else None,
        )
    except GovernanceContextMaterializationError as e:
        return {
            "blocked": True,
            "reason": f"governance-context-materialization-failed: {e.reason}",
            "reason_code": e.reason_code,
            "recovery_action": "Failed to materialize governance artifacts.",
            "binding_resolved": has_executor,
            "invoke_backend_available": has_executor,
        }

    developer_schema_text = _get_developer_output_schema_text()
    structured_output_instruction = ""
    if developer_schema_text:
        structured_output_instruction = (
            "\n\nSTRUCTURED OUTPUT REQUIRED:\n"
            "You MUST respond with valid JSON that conforms to the output schema below.\n"
            "Do NOT include any text outside the JSON object.\n\n"
            "Output schema:\n" + developer_schema_text
        )

    context: dict[str, object] = {
        "schema": "opencode.implement.llm-context.v4",
        "ticket": ticket_text,
        "task": task_text,
        "approved_plan": plan_text,
        "required_hotspots": required_hotspots,
        "phase": get_phase(state),
        "active_gate": str(state.get("active_gate") or ""),
        "next_gate_condition": str(state.get("next_gate_condition") or ""),
        "forbidden_paths": [".governance/"],
        "requirements": {
            "domain_diff_required": True,
            "plan_step_coverage_required": True,
            "targeted_checks_required": True,
        },
    }
    if materialization.plan_mandate_file:
        context["authoring_mandate_file"] = str(materialization.plan_mandate_file)
        context["authoring_mandate_sha256"] = materialization.plan_mandate_sha256
        context["authoring_mandate_label"] = materialization.plan_mandate_label
    if materialization.effective_policy_file:
        context["effective_policy_file"] = str(materialization.effective_policy_file)
        context["effective_policy_sha256"] = materialization.effective_policy_sha256
        context["effective_policy_label"] = materialization.effective_policy_label
    if materialization.has_materialized():
        context["effective_policy_loaded"] = True
    elif effective_policy_error:
        context["effective_policy_error"] = effective_policy_error

    if materialization.has_materialized():
        instruction_parts = []
        if materialization.plan_mandate_file:
            instruction_parts.append(
                f"Load the authoring mandate from file: {materialization.plan_mandate_file} "
                f"(SHA256: {materialization.plan_mandate_sha256})"
            )
        if materialization.effective_policy_file:
            instruction_parts.append(
                f"Load the effective policy from file: {materialization.effective_policy_file} "
                f"(SHA256: {materialization.effective_policy_sha256})"
            )
        instruction_parts.append(
            "Build only what can be justified by the plan, contracts, and repository evidence."
        )
        instruction_parts.append("Do not limit changes to .governance artifacts.")
        instruction_parts.append(structured_output_instruction)
        context["instruction"] = "\n".join(instruction_parts)
    else:
        context["instruction"] = (
            "Implement approved plan steps using repository edits. "
            "Do not limit changes to .governance artifacts."
            + structured_output_instruction
        )
    if materialization.has_materialized():
        context["context_materialization_complete"] = True
    _write_text_atomic(context_file, json.dumps(context, ensure_ascii=True, indent=2) + "\n")

    try:
        validate_materialized_artifacts(materialization)
    except GovernanceContextMaterializationError as e:
        return {
            "blocked": True,
            "reason": f"governance-context-validation-failed: {e.reason}",
            "reason_code": e.reason_code,
            "recovery_action": "Materialized artifacts failed validation.",
            "binding_resolved": has_executor,
            "invoke_backend_available": has_executor,
        }

    repo_baseline = _capture_repo_change_baseline(repo_root)
    before_changed = set(_parse_changed_files_from_git_status(repo_root))
    before_hotspot_hashes = _capture_hotspot_hashes(repo_root, required_hotspots)

    bridge_mode = False
    if not executor_cmd:
        if _has_active_desktop_llm_binding() and not pipeline_mode:
            bridge_cmd = _resolve_desktop_executor_bridge_cmd(repo_root=repo_root)
            if bridge_cmd:
                executor_cmd = bridge_cmd
                bridge_mode = True
            else:
                _write_text_atomic(stdout_file, "")
                _write_text_atomic(
                    stderr_file,
                    (
                        "Direct mode requires active chat binding and callable desktop bridge.\n"
                    ),
                )
                return {
                    "executor_invoked": False,
                    "exit_code": 2,
                    "reason_code": RC_EXECUTOR_NOT_CONFIGURED,
                    "binding_resolved": True,
                    "invoke_backend_available": False,
                    "message": (
                        "Direct mode binding resolved to active chat binding, but no callable desktop bridge with a resolvable session id is available in this shell process."
                    ),
                    "stdout_path": str(stdout_file),
                    "stderr_path": str(stderr_file),
                    "changed_files": [],
                    "repo_baseline": repo_baseline,
                    "blocked": True,
                }
        if not executor_cmd:
            _write_text_atomic(stdout_file, "")
            _write_text_atomic(stderr_file, "LLM executor command missing\n")
            return {
                "executor_invoked": False,
                "exit_code": 2,
                "reason_code": RC_EXECUTOR_NOT_CONFIGURED,
                "binding_resolved": False,
                "invoke_backend_available": False,
                "message": "No implementation execution binding available for active mode.",
                "stdout_path": str(stdout_file),
                "stderr_path": str(stderr_file),
                "changed_files": [],
                "repo_baseline": repo_baseline,
                "blocked": True,
            }

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))

    try:
        result = subprocess.run(
            final_cmd,
            shell=True,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            env=_build_executor_env(bridge_mode=bridge_mode),
            timeout=_bridge_timeout_seconds() if bridge_mode else None,
        )
    except subprocess.TimeoutExpired:
        _write_text_atomic(stdout_file, "")
        _write_text_atomic(stderr_file, "implementation-llm-timeout\n")
        return {
            "executor_invoked": True,
            "exit_code": 124,
            "reason_code": RC_EXECUTOR_FAILED,
            "binding_resolved": True,
            "invoke_backend_available": True,
            "message": "Implementation LLM bridge timed out.",
            "stdout_path": str(stdout_file),
            "stderr_path": str(stderr_file),
            "changed_files": [],
            "repo_baseline": repo_baseline,
            "blocked": True,
        }
    _write_text_atomic(stdout_file, str(result.stdout or ""))
    _write_text_atomic(stderr_file, str(result.stderr or ""))

    validation_violations: list[str] = []
    response_valid = False
    response_text = (result.stdout or "").strip()

    response_text = _parse_json_events_to_text(response_text)

    if bridge_mode:
        response_valid = True
    elif response_text and response_text.startswith("{"):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "governance_runtime" / "application" / "validators"))
        try:
            from llm_response_validator import validate_developer_response
            parsed = json.loads(response_text)
            validation = validate_developer_response(parsed, mandates_schema=schema)
            if validation.valid:
                response_valid = True
            else:
                validation_violations = validation.raw_violations
        except json.JSONDecodeError:
            validation_violations = ["response-not-structured-json"]
        except (OSError, IOError) as e:
            validation_violations = [f"response-read-error: {e}"]
    else:
        if response_text:
            validation_violations = ["response-not-structured-json"]

    after_changed = set(_parse_changed_files_from_git_status(repo_root))
    delta_changed = sorted(after_changed - before_changed)
    after_hotspot_hashes = _capture_hotspot_hashes(repo_root, required_hotspots)
    hotspot_changed = sorted(
        path
        for path in sorted(set(before_hotspot_hashes).union(after_hotspot_hashes))
        if before_hotspot_hashes.get(path, "") != after_hotspot_hashes.get(path, "")
    )
    changed_files = sorted(set(delta_changed).union(hotspot_changed))
    return {
        "executor_invoked": True,
        "exit_code": int(result.returncode),
        "reason_code": "" if result.returncode == 0 else RC_EXECUTOR_FAILED,
        "message": "" if result.returncode == 0 else str(result.stderr or result.stdout or "").strip(),
        "stdout_path": str(stdout_file),
        "stderr_path": str(stderr_file),
        "changed_files": changed_files,
        "response_valid": response_valid,
        "validation_violations": validation_violations,
        "bridge_mode": bridge_mode,
        "binding_resolved": True,
        "invoke_backend_available": True,
        "repo_baseline": repo_baseline,
    }


def _run_targeted_checks(repo_root: Path, requirements: list[dict[str, object]]) -> tuple[tuple[CheckResult, ...], bool]:
    tests: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        acceptance = requirement.get("acceptance_tests")
        if not isinstance(acceptance, list):
            continue
        for item in acceptance:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            tests.append(token)

    if not tests:
        return (), False

    valid_tests: list[str] = [token for token in tests if _selector_target_exists(repo_root, token)]
    executed_tests = valid_tests
    if not executed_tests:
        executed_tests = _derive_targeted_check_fallbacks(repo_root, requirements)
    if not executed_tests:
        return (), False

    command = ["python3", "-m", "pytest", "-q", *executed_tests]
    result = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, check=False)
    output_file = repo_root / ".governance" / "implementation" / "targeted_checks.log"
    output = (result.stdout or "") + ("\n" if result.stdout and result.stderr else "") + (result.stderr or "")
    if len(valid_tests) != len(tests):
        ignored = sorted(set(tests) - set(valid_tests))
        if ignored:
            output = (
                "[implement] ignored invalid acceptance test selectors:\n"
                + "\n".join(ignored)
                + "\n\n"
                + output
            )
    if executed_tests != valid_tests and executed_tests:
        output = (
            "[implement] fallback targeted checks executed:\n"
            + "\n".join(executed_tests)
            + "\n\n"
            + output
        )
    _write_text_atomic(output_file, output)
    failure_kind = _classify_check_failure_kind(int(result.returncode), output)
    check_results = tuple(
        CheckResult(
            name=test,
            passed=result.returncode == 0,
            exit_code=int(result.returncode),
            output_path=str(output_file),
            failure_kind=failure_kind,
        )
        for test in executed_tests
    )
    return check_results, True


def _user_review_decision(state: Mapping[str, object]) -> str:
    decision = state.get("UserReviewDecision")
    if isinstance(decision, Mapping):
        value = decision.get("decision")
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"approve", "changes_requested", "reject"}:
                return token
    value = state.get("user_review_decision")
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"approve", "changes_requested", "reject"}:
            return token
    return ""


def start_implementation(
    *,
    session_path: Path,
    events_path: Path | None = None,
    actor: str = "",
    note: str = "",
) -> dict[str, object]:
    if not session_path.exists():
        return _payload("error", reason_code=BLOCKED_IMPLEMENT_START_INVALID, message="session state file not found")

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    enforcement = require_complete_contracts(
        repo_root=Path(__file__).absolute().parents[2],
        required_ids=("R-IMPLEMENT-001",),
    )
    if not enforcement.ok:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"{enforcement.reason}: {';'.join(enforcement.details)}",
        )

    phase_text = get_phase(state).strip()
    if not phase_text.startswith("6"):
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"/implement is only allowed in Phase 6. Current phase: {phase_text or 'unknown'}",
        )

    decision = _user_review_decision(state)
    workflow_complete = bool(state.get("workflow_complete") or state.get("WorkflowComplete"))
    if decision != "approve" and not workflow_complete:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires an approved final review decision at Workflow Complete.",
        )

    active_gate = get_active_gate(state).strip().lower()
    if active_gate == "rework clarification gate":
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement is blocked while rework clarification is pending.",
        )
    if active_gate == "ticket input gate":
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement is blocked after rejection/restart routing. Re-enter via /ticket.",
        )

    signal = resolve_plan_record_signal(state=state, plan_record_file=session_path.parent / "plan-record.json")
    if signal.versions < 1:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires persisted plan-record evidence.",
        )

    contracts_present = bool(state.get("requirement_contracts_present"))
    try:
        contracts_count = int(str(state.get("requirement_contracts_count") or "0").strip())
    except ValueError:
        contracts_count = 0
    if not contracts_present or contracts_count < 1:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires compiled requirement contracts from /plan before execution can start.",
        )

    event_id = uuid.uuid4().hex
    ts = _now_iso()
    phase_before = phase_text
    gate_before = get_active_gate(state)
    if events_path is not None:
        _append_event(
            events_path,
            {
                "schema": "opencode.rail-lifecycle.v1",
                "ts_utc": ts,
                "event_id": uuid.uuid4().hex,
                "event": "RAIL_STARTED",
                "rail": "implement",
                "phase_before": phase_before,
                "gate_before": gate_before,
            },
        )
    plan_record_file = session_path.parent / "plan-record.json"
    plan_text = _latest_plan_text(plan_record_file, state=state)
    canonical_state = normalize_to_canonical(state)
    ticket_text = str(
        canonical_state.get("ticket")
        or state.get("Ticket")
        or state.get("ticket")
        or ""
    ).strip()
    task_text = str(
        canonical_state.get("task")
        or state.get("Task")
        or state.get("task")
        or ""
    ).strip()
    repo_root = _repo_root(session_path, state)
    compiled_requirements = _load_compiled_requirements(session_path, state)
    source_authority = _load_compiled_requirements_source_authority(session_path, state)
    state["requirement_contracts_source_authority_observed"] = source_authority
    allowed_sources = {"machine_requirements"}
    if _allow_legacy_requirement_source():
        allowed_sources.add("legacy_markdown_requirements")
    if source_authority and source_authority not in allowed_sources:
        return _payload(
            "error",
            reason_code="REQUIREMENT_SOURCE_INVALID",
            message=(
                "Compiled requirements source authority is invalid for /implement. "
                f"observed={source_authority}, expected one of {sorted(allowed_sources)}"
            ),
        )
    required_hotspots = _extract_hotspot_files(compiled_requirements)

    resolver = BindingEvidenceResolver(env=os.environ)
    evidence = getattr(resolver, "resolve")(mode="user")
    commands_home = evidence.commands_home

    # Resolve mode-scoped execution binding.
    workspace_dir = session_path.parent
    workspaces_home: Path | None = None
    active_repo_fingerprint: str | None = None
    pipeline_mode = False
    execution_binding = ""
    execution_binding_source = ""
    try:
        resolved_session_path, resolved_repo_fingerprint, resolved_workspaces_home, resolved_workspace_dir = resolve_active_session_paths()
        if resolved_session_path == session_path:
            workspace_dir = resolved_workspace_dir
            workspaces_home = resolved_workspaces_home
            active_repo_fingerprint = resolved_repo_fingerprint
    except Exception:
        pass

    pipeline_mode = get_pipeline_mode(workspace_dir)
    try:
        binding = resolve_governance_binding(
            role="execution",
            workspace_root=workspace_dir,
            env_reader=lambda key: os.environ.get(key),
            has_active_chat_binding=_has_active_desktop_llm_binding(),
        )
        execution_binding = str(binding.binding_value or "").strip()
        execution_binding_source = str(binding.source or "").strip()
    except GovernanceBindingResolutionError as exc:
        reason_code = RC_EXECUTOR_NOT_CONFIGURED
        message = str(exc)
        state["implementation_authorized"] = True
        state["implementation_started"] = True
        state["implementation_started_at"] = ts
        state["implementation_started_by"] = actor.strip() or "operator"
        state["implementation_execution_started"] = False
        state["implementation_pipeline_mode"] = pipeline_mode
        state["implementation_binding_role"] = "execution"
        state["implementation_binding_resolved"] = False
        state["implementation_invoke_backend_available"] = False
        state["next"] = "6"
        state["active_gate"] = "Implementation Blocked"
        state["status"] = "blocked"
        state["next_gate_condition"] = "Implementation binding resolution failed for active mode."
        _write_json_atomic(session_path, state_doc)
        if events_path is not None:
            _append_event(
                events_path,
                {
                    "schema": "opencode.implementation-started.v2",
                    "ts_utc": ts,
                    "event_id": event_id,
                    "event": "IMPLEMENTATION_BLOCKED_PRECHECK",
                    "phase": phase_text,
                    "reason_code": reason_code,
                    "message": message,
                    "pipeline_mode": pipeline_mode,
                    "binding_role": "execution",
                    "binding_source": execution_binding_source,
                    "binding_resolved": False,
                    "invoke_backend_available": False,
                },
            )
        return _payload(
            "blocked",
            reason_code=reason_code,
            message=message,
            phase="6-PostFlight",
            next="6",
            active_gate="Implementation Blocked",
            next_gate_condition=state["next_gate_condition"],
            reason_codes=[reason_code],
            pipeline_mode=pipeline_mode,
            binding_role="execution",
            binding_source=execution_binding_source,
            binding_resolved=False,
            invoke_backend_available=False,
            next_action="Set AI_GOVERNANCE_EXECUTION_BINDING and AI_GOVERNANCE_REVIEW_BINDING and rerun /implement.",
        )

    llm_result = _run_llm_edit_step(
        repo_root=repo_root,
        state=state,
        ticket_text=ticket_text,
        task_text=task_text,
        plan_text=plan_text,
        required_hotspots=required_hotspots,
        commands_home=commands_home,
        config_root=evidence.config_root,
        workspaces_home=workspaces_home,
        repo_fingerprint=active_repo_fingerprint,
        pipeline_mode=pipeline_mode,
        execution_binding=execution_binding,
    )

    if bool(llm_result.get("blocked")):
        reason_code = str(llm_result.get("reason_code") or "IMPLEMENTATION_LLM_PRECHECK_BLOCKED").strip()
        message = str(llm_result.get("message") or llm_result.get("reason") or "LLM precheck blocked").strip()
        binding_resolved = bool(llm_result.get("binding_resolved", True))
        invoke_backend_available = bool(llm_result.get("invoke_backend_available", True))
        if not message:
            message = "LLM precheck blocked"
        state["implementation_authorized"] = True
        state["implementation_started"] = True
        state["implementation_started_at"] = ts
        state["implementation_started_by"] = actor.strip() or "operator"
        state["implementation_execution_started"] = False
        state["implementation_pipeline_mode"] = pipeline_mode
        state["implementation_binding_role"] = "execution"
        state["implementation_binding_resolved"] = binding_resolved
        state["implementation_invoke_backend_available"] = invoke_backend_available
        if execution_binding_source:
            state["implementation_binding_source"] = execution_binding_source
        state["next"] = "6"
        state["active_gate"] = "Implementation Blocked"
        state["status"] = "blocked"
        if reason_code == RC_EXECUTOR_NOT_CONFIGURED:
            state["next_gate_condition"] = (
                "Implementation executor unavailable in current process. "
                "Provide required governance bindings for active mode and rerun /implement."
            )
        else:
            state["next_gate_condition"] = (
                f"Implementation precheck failed ({reason_code}). {message}. Resolve and rerun /implement."
            )
        _write_json_atomic(session_path, state_doc)
        if events_path is not None:
            _append_event(
                events_path,
                {
                    "schema": "opencode.implementation-started.v2",
                    "ts_utc": ts,
                    "event_id": event_id,
                    "event": "IMPLEMENTATION_BLOCKED_PRECHECK",
                    "phase": phase_text,
                    "reason_code": reason_code,
                    "message": message,
                    "pipeline_mode": pipeline_mode,
                    "binding_role": "execution",
                    "binding_source": execution_binding_source,
                    "binding_resolved": binding_resolved,
                    "invoke_backend_available": invoke_backend_available,
                },
            )
            _append_event(
                events_path,
                {
                    "schema": "opencode.rail-lifecycle.v1",
                    "ts_utc": ts,
                    "event_id": uuid.uuid4().hex,
                    "event": "RAIL_BLOCKED",
                    "rail": "implement",
                    "phase_before": phase_before,
                    "gate_before": gate_before,
                    "phase_after": "6-PostFlight",
                    "gate_after": "Implementation Blocked",
                    "primary_reason_code": reason_code,
                    "secondary_reason_codes": [],
                    "state_delta": {
                        "status": "blocked",
                        "active_gate": "Implementation Blocked",
                    },
                    "evidence_refs": [
                        {
                            "path": str(llm_result.get("stderr_path") or ""),
                            "evidence_type": "executor_stderr",
                            "content_role": "diagnostic",
                        }
                    ],
                },
            )
        return _payload(
            "blocked",
            event_id=event_id,
            phase="6-PostFlight",
            next="6",
            active_gate="Implementation Blocked",
            next_gate_condition=state["next_gate_condition"],
            implementation_started=True,
            implementation_validation={
                "executor_invoked": False,
                "executor_succeeded": False,
                "has_domain_diffs": False,
                "governance_only_changes": False,
                "changed_files": [],
                "domain_changed_files": [],
                "plan_coverage": [],
                "checks": [],
                "reason_codes": [reason_code],
                "is_compliant": False,
            },
            reason_code=reason_code,
            reason_codes=[reason_code],
            pipeline_mode=pipeline_mode,
            binding_role="execution",
            binding_source=execution_binding_source,
            binding_resolved=binding_resolved,
            invoke_backend_available=invoke_backend_available,
            repo_baseline=llm_result.get("repo_baseline") if isinstance(llm_result, Mapping) else None,
            next_action=(
                "Provide required governance bindings for active mode and rerun /implement."
                if reason_code == RC_EXECUTOR_NOT_CONFIGURED
                else "Resolve the precheck blocker and rerun /implement."
            ),
        )

    validation_violations = llm_result.get("validation_violations") or []
    response_valid = bool(llm_result.get("response_valid"))

    if validation_violations:
        _impl_dir = repo_root / ".governance" / "implementation"
        _impl_dir.mkdir(parents=True, exist_ok=True)
        report = validate_implementation(
            executor_result=ExecutorRunResult(
                executor_invoked=bool(llm_result.get("executor_invoked")),
                exit_code=int(str(llm_result.get("exit_code") or "0")),
                stdout_path=str(llm_result.get("stdout_path") or "") or None,
                stderr_path=str(llm_result.get("stderr_path") or "") or None,
                changed_files=(),
                domain_changed_files=(),
                governance_only_changes=True,
            ),
            plan_coverage=build_plan_coverage(
                requirements=compiled_requirements,
                domain_changed_files=tuple(),
            ),
            checks=(),
            forbidden_paths_changed=False,
        )
        validation_report_path = _impl_dir / "implementation_validation_report.json"
        write_validation_report(validation_report_path, report)

        state["implementation_authorized"] = True
        state["implementation_started"] = True
        state["implementation_started_at"] = ts
        state["implementation_started_by"] = actor.strip() or "operator"
        state["implementation_execution_started"] = True
        state["implementation_validation_report"] = to_report_payload(report)
        state["implementation_validation_report_path"] = str(validation_report_path)
        state["implementation_llm_response_valid"] = response_valid
        state["implementation_llm_validation_violations"] = validation_violations
        state["implementation_binding_resolved"] = bool(llm_result.get("binding_resolved", True))
        state["implementation_invoke_backend_available"] = bool(
            llm_result.get("invoke_backend_available", True)
        )
        state["next"] = "6"
        state["active_gate"] = "Implementation Blocked"
        state["next_gate_condition"] = (
            "Implementation blocked: LLM response failed validation. "
            f"violations={validation_violations}. Rerun with a schema-compliant response."
        )
        _write_json_atomic(session_path, state_doc)
        audit_event: dict[str, object] = {
            "schema": "opencode.implementation-started.v2",
            "ts_utc": ts,
            "event_id": uuid.uuid4().hex,
            "event": "IMPLEMENTATION_BLOCKED_VALIDATION",
            "phase": phase_text,
            "actor": actor.strip() or "operator",
            "validation_violations": validation_violations,
            "pipeline_mode": pipeline_mode,
            "binding_role": "execution",
            "binding_source": execution_binding_source,
            "binding_resolved": bool(llm_result.get("binding_resolved", True)),
            "invoke_backend_available": bool(llm_result.get("invoke_backend_available", True)),
        }
        if events_path is not None:
            _append_event(events_path, audit_event)
            _append_event(
                events_path,
                {
                    "schema": "opencode.rail-lifecycle.v1",
                    "ts_utc": ts,
                    "event_id": uuid.uuid4().hex,
                    "event": "RAIL_BLOCKED",
                    "rail": "implement",
                    "phase_before": phase_before,
                    "gate_before": gate_before,
                    "phase_after": "6-PostFlight",
                    "gate_after": "Implementation Blocked",
                    "primary_reason_code": "LLM_RESPONSE_VALIDATION_FAILED",
                    "secondary_reason_codes": list(validation_violations),
                    "state_delta": {
                        "status": "blocked",
                        "active_gate": "Implementation Blocked",
                    },
                    "evidence_refs": [
                        {
                            "path": str(validation_report_path),
                            "evidence_type": "implementation_validation_report",
                            "content_role": "validation",
                        }
                    ],
                },
            )
        return _payload(
            "blocked",
            phase="6-PostFlight",
            next="6",
            active_gate="Implementation Blocked",
            next_gate_condition=state["next_gate_condition"],
            implementation_started=True,
            implementation_validation=to_report_payload(report),
            implementation_llm_response_valid=response_valid,
            implementation_llm_validation_violations=validation_violations,
            reason_code="LLM_RESPONSE_VALIDATION_FAILED",
            reason_codes=validation_violations,
            pipeline_mode=pipeline_mode,
            binding_role="execution",
            binding_source=execution_binding_source,
            binding_resolved=bool(llm_result.get("binding_resolved", True)),
            invoke_backend_available=bool(llm_result.get("invoke_backend_available", True)),
            repo_baseline=llm_result.get("repo_baseline") if isinstance(llm_result, Mapping) else None,
        )

    changed_files_raw = llm_result.get("changed_files")
    changed_files_seq = changed_files_raw if isinstance(changed_files_raw, list) else []
    changed_files = tuple(str(item).strip().replace("\\", "/") for item in changed_files_seq if str(item).strip())
    domain_changed = split_domain_changed_files(
        changed_files,
        forbidden_prefixes=(".governance/",),
    )
    executor_result = ExecutorRunResult(
        executor_invoked=bool(llm_result.get("executor_invoked")),
        exit_code=int(str(llm_result.get("exit_code") or "0")),
        stdout_path=str(llm_result.get("stdout_path") or "") or None,
        stderr_path=str(llm_result.get("stderr_path") or "") or None,
        changed_files=changed_files,
        domain_changed_files=domain_changed,
        governance_only_changes=bool(changed_files) and len(domain_changed) == 0,
    )

    check_results, checks_declared = _run_targeted_checks(repo_root, compiled_requirements)
    if not checks_declared:
        check_results = ()

    plan_coverage = build_plan_coverage(
        requirements=compiled_requirements,
        domain_changed_files=domain_changed,
    )
    forbidden_paths_changed = any(path.startswith(".governance/") for path in domain_changed)
    report = validate_implementation(
        executor_result=executor_result,
        plan_coverage=plan_coverage,
        checks=check_results,
        forbidden_paths_changed=forbidden_paths_changed,
    )

    implementation_dir = repo_root / ".governance" / "implementation"
    implementation_dir.mkdir(parents=True, exist_ok=True)
    report_path = implementation_dir / "implementation_validation_report.json"
    write_validation_report(report_path, report)

    state["implementation_authorized"] = True
    state["implementation_started"] = True
    state["implementation_started_at"] = ts
    state["implementation_started_by"] = actor.strip() or "operator"
    state["implementation_start_note"] = note.strip()
    state["implementation_execution_started"] = True
    state["implementation_validation_report"] = to_report_payload(report)
    state["implementation_validation_report_path"] = str(report_path)
    state["implementation_checks_executed"] = [item.name for item in report.checks]
    state["implementation_checks_ok"] = bool(report.checks) and all(item.passed for item in report.checks)
    state["implementation_changed_files"] = list(report.changed_files)
    state["implementation_domain_changed_files"] = list(report.domain_changed_files)
    state["implementation_required_hotspots"] = required_hotspots
    state["implementation_llm_step_executed"] = report.executor_invoked
    state["implementation_execution_status"] = "review_complete" if report.is_compliant else "blocked"
    state["implementation_status"] = "ready_for_review" if report.is_compliant else "blocked"
    state["implementation_primary_reason_code"] = report.primary_reason_code
    state["implementation_secondary_reason_codes"] = list(report.secondary_reason_codes)
    state["implementation_reason_codes"] = list(report.reason_codes)
    baseline = llm_result.get("repo_baseline")
    if isinstance(baseline, Mapping):
        state["repo_dirty_before"] = bool(baseline.get("repo_dirty_before"))
        tracked_before = baseline.get("tracked_changes_before")
        untracked_before = baseline.get("untracked_before")
        if isinstance(tracked_before, list):
            state["tracked_changes_before"] = [str(x) for x in tracked_before]
        if isinstance(untracked_before, list):
            state["untracked_before"] = [str(x) for x in untracked_before]
    state["implementation_pipeline_mode"] = pipeline_mode
    state["implementation_binding_role"] = "execution"
    state["implementation_binding_resolved"] = bool(llm_result.get("binding_resolved", True))
    state["implementation_invoke_backend_available"] = bool(
        llm_result.get("invoke_backend_available", True)
    )
    if execution_binding_source:
        state["implementation_binding_source"] = execution_binding_source
    state["next"] = "6"

    if report.is_compliant:
        state["active_gate"] = "Implementation Review Complete"
        state["status"] = "OK"
        state["next_gate_condition"] = "Implementation validation passed. Run /continue."
    else:
        state["active_gate"] = "Implementation Blocked"
        state["status"] = "blocked"
        reason_text = ", ".join(report.reason_codes) if report.reason_codes else RC_TARGETED_CHECKS_MISSING
        state["next_gate_condition"] = (
            "Implementation validation failed. "
            f"primary_reason={report.primary_reason_code or RC_TARGETED_CHECKS_MISSING}; "
            f"reason_codes={reason_text}. Resolve blockers and rerun /implement."
        )

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.implementation-started.v2",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "IMPLEMENTATION_STARTED",
        "phase": phase_text,
        "decision": decision or "approve",
        "plan_record_versions": signal.versions,
        "actor": state["implementation_started_by"],
        "validation": to_report_payload(report),
        "primary_reason_code": report.primary_reason_code,
        "secondary_reason_codes": list(report.secondary_reason_codes),
        "pipeline_mode": pipeline_mode,
        "binding_role": "execution",
        "binding_source": execution_binding_source,
        "binding_resolved": bool(llm_result.get("binding_resolved", True)),
        "invoke_backend_available": bool(llm_result.get("invoke_backend_available", True)),
    }
    if events_path is not None:
        _append_event(events_path, audit_event)
        _append_event(
            events_path,
            {
                "schema": "opencode.rail-lifecycle.v1",
                "ts_utc": ts,
                "event_id": uuid.uuid4().hex,
                "event": "RAIL_COMPLETED" if report.is_compliant else "RAIL_BLOCKED",
                "rail": "implement",
                "phase_before": phase_before,
                "gate_before": gate_before,
                "phase_after": "6-PostFlight",
                "gate_after": str(state.get("active_gate") or ""),
                "primary_reason_code": report.primary_reason_code,
                "secondary_reason_codes": list(report.secondary_reason_codes),
                "state_delta": {
                    "status": str(state.get("status") or ""),
                    "active_gate": str(state.get("active_gate") or ""),
                    "implementation_status": str(state.get("implementation_status") or ""),
                },
                "evidence_refs": [
                    {
                        "path": str(report_path),
                        "evidence_type": "implementation_validation_report",
                        "content_role": "validation",
                    },
                    {
                        "path": str(state.get("implementation_validation_report_path") or ""),
                        "evidence_type": "implementation_validation_report",
                        "content_role": "state_reference",
                    },
                ],
            },
        )

    payload = _payload(
        "ok" if report.is_compliant else "blocked",
        event_id=event_id,
        phase="6-PostFlight",
        next="6",
        active_gate=str(state.get("active_gate") or "Implementation Blocked"),
        next_gate_condition=state["next_gate_condition"],
        implementation_started=True,
        implementation_validation=to_report_payload(report),
        implementation_changed_files=list(report.changed_files),
        implementation_domain_changed_files=list(report.domain_changed_files),
        implementation_checks_executed=[item.name for item in report.checks],
        implementation_checks_ok=bool(report.checks) and all(item.passed for item in report.checks),
        pipeline_mode=pipeline_mode,
        binding_role="execution",
        binding_source=execution_binding_source,
        binding_resolved=bool(llm_result.get("binding_resolved", True)),
        invoke_backend_available=bool(llm_result.get("invoke_backend_available", True)),
        repo_baseline=llm_result.get("repo_baseline") if isinstance(llm_result, Mapping) else None,
        next_action=(
            "run /continue."
            if report.is_compliant
            else "run configured LLM executor, produce domain diffs, satisfy plan coverage, and pass targeted checks."
        ),
    )
    if not report.is_compliant:
        payload["primary_reason_code"] = report.primary_reason_code
        payload["secondary_reason_codes"] = list(report.secondary_reason_codes)
        payload["reason_codes"] = list(report.reason_codes)
        primary_reason = report.primary_reason_code or "IMPLEMENTATION_VALIDATION_FAILED"
        payload["reason_code"] = primary_reason
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist /implement governance-to-implementation handoff")
    parser.add_argument("--actor", default="", help="Optional operator identifier")
    parser.add_argument("--note", default="", help="Optional handoff note")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        payload = start_implementation(
            session_path=session_path,
            events_path=events_path,
            actor=str(args.actor),
            note=str(args.note),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"implement start failed: {exc}",
        )

    status = str(payload.get("status") or "error").strip().lower()
    print(json.dumps(payload, ensure_ascii=True))
    if status == "ok":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
