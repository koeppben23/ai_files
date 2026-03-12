#!/usr/bin/env python3
"""Implementation execution rail -- ``/implement`` entrypoint.

Runs implementation execution from the approved plan, performs an internal
review/revision/verification loop, and persists a presentation-ready package
or a fail-closed blocked state.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
import hashlib
import re
import os
import subprocess
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.plan_record_state import resolve_plan_record_signal
from governance.contracts.enforcement import require_complete_contracts

BLOCKED_IMPLEMENT_START_INVALID = "BLOCKED-UNSPECIFIED"
_GOVERNANCE_META_TOKENS = (
    "governance",
    "phase",
    "gate",
    "review",
    "plan record",
    "decision semantics",
    "state-machine",
    "audit",
    "reason-code",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json root must be object")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    atomic_write_text(path, text)


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


def _latest_plan_text(plan_record_file: Path) -> str:
    if not plan_record_file.exists():
        return ""
    payload = _load_json(plan_record_file)
    versions = payload.get("versions")
    if not isinstance(versions, list) or not versions:
        return ""
    latest = versions[-1] if isinstance(versions[-1], dict) else {}
    if not isinstance(latest, dict):
        return ""
    return str(latest.get("plan_record_text") or "").strip()


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


def _is_governance_meta(text: str) -> bool:
    lower = text.strip().lower()
    return any(token in lower for token in _GOVERNANCE_META_TOKENS)


def _extract_action_lines(text: str) -> list[str]:
    actions: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        elif line[:3].isdigit() and "." in line[:4]:
            line = line.split(".", 1)[1].strip()
        if line:
            actions.append(line)
    return actions


def _build_execution_work_queue(plan_text: str, state: Mapping[str, object], contract_titles: list[str]) -> list[str]:
    queue: list[str] = []

    queue.extend(_extract_action_lines(str(state.get("Ticket") or "")))
    queue.extend(_extract_action_lines(str(state.get("Task") or "")))

    for title in contract_titles:
        value = str(title).strip()
        if value and not _is_governance_meta(value):
            queue.append(value)

    for line in _extract_action_lines(plan_text):
        if not _is_governance_meta(line):
            queue.append(line)

    if not queue:
        queue = [
            "Identify files affected by ticket requirements",
            "Apply implementation changes in repo target files",
            "Run focused verification for touched areas",
        ]

    deduped: list[str] = []
    seen: set[str] = set()
    for item in queue:
        key = " ".join(item.split()).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:20]


def _repo_root(session_path: Path, state: Mapping[str, object]) -> Path:
    explicit = str(state.get("RepoRoot") or state.get("repo_root") or "").strip()
    if explicit:
        root = Path(explicit)
        if root.is_absolute() and root.exists() and root.is_dir():
            return root
    if session_path.parent.exists() and session_path.parent.is_dir():
        return session_path.parent
    cwd = Path(os.path.abspath(str(Path.cwd())))
    if (cwd / ".git").exists():
        return cwd
    for parent in cwd.parents:
        if (parent / ".git").exists():
            return parent
    return session_path.parent


def _extract_candidate_files(plan_text: str, repo_root: Path) -> list[Path]:
    pattern = re.compile(r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_-]+")
    found: list[Path] = []
    seen: set[str] = set()
    for token in pattern.findall(plan_text):
        normalized = token.strip().strip("`\"'")
        if not normalized or normalized.startswith("../"):
            continue
        candidate = Path(os.path.abspath(str(repo_root / normalized)))
        try:
            candidate.relative_to(repo_root)
        except Exception:
            continue
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            found.append(candidate)
    return found[:3]


def _extract_hotspot_files(requirements: list[dict[str, object]], repo_root: Path) -> list[Path]:
    seen: set[str] = set()
    files: list[Path] = []
    for requirement in requirements:
        hotspots = requirement.get("code_hotspots")
        if not isinstance(hotspots, list):
            continue
        for hotspot in hotspots:
            token = str(hotspot or "").strip()
            if not token or token.startswith(".."):
                continue
            path = Path(os.path.abspath(str(repo_root / token)))
            try:
                path.relative_to(repo_root)
            except ValueError:
                continue
            if not path.exists() or not path.is_file():
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    return files[:12]


def _clean_replacement_token(value: str) -> str:
    token = str(value or "").strip().strip('"\'`')
    return " ".join(token.split())


def _extract_literal_replacements(text: str) -> list[tuple[str, str]]:
    patterns = (
        r"nicht mehr\s+(?:im\s+ordner\s+)?(?P<old>[^,.;]+?),\s*sondern\s+(?:unter\s+)?(?P<new>[^.;]+)",
        r"von\s+(?P<old>[^,.;]+?)\s+nach\s+(?P<new>[^.;]+)",
        r"from\s+(?P<old>[^,.;]+?)\s+to\s+(?P<new>[^.;]+)",
        r"move\s+(?P<old>[^,.;]+?)\s+to\s+(?P<new>[^.;]+)",
    )
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    source = str(text or "")
    for pattern in patterns:
        for match in re.finditer(pattern, source, flags=re.IGNORECASE):
            old = _clean_replacement_token(match.group("old"))
            new = _clean_replacement_token(match.group("new"))
            if not old or not new or old == new:
                continue
            pair = (old, new)
            if pair in seen:
                continue
            seen.add(pair)
            out.append(pair)
    return out


def _domain_changed_files(changed_files: list[Path], repo_root: Path) -> list[str]:
    domain: list[str] = []
    for path in changed_files:
        rel = str(Path(os.path.abspath(str(path))).relative_to(repo_root))
        if rel.startswith(".governance/"):
            continue
        domain.append(rel)
    return domain


def _git_path_visible_in_status(repo_root: Path, rel_path: str) -> bool | None:
    if not rel_path.strip():
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain", "--", rel_path],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return bool(str(result.stdout or "").strip())


def _run_llm_edit_step(
    *,
    repo_root: Path,
    state: Mapping[str, object],
    ticket_text: str,
    task_text: str,
    plan_text: str,
    required_hotspots: list[str],
) -> dict[str, object]:
    executor_cmd = str(os.environ.get("OPENCODE_IMPLEMENT_LLM_CMD") or "").strip()
    if not executor_cmd:
        return {
            "ok": False,
            "reason_code": "IMPLEMENTATION-LLM-EXECUTOR-NOT-CONFIGURED",
            "message": "Set OPENCODE_IMPLEMENT_LLM_CMD to execute LLM-based repository edits.",
            "changed_files": [],
            "llm_step_executed": False,
        }

    implementation_dir = repo_root / ".governance" / "implementation"
    implementation_dir.mkdir(parents=True, exist_ok=True)
    context_file = implementation_dir / "llm_edit_context.json"
    context = {
        "schema": "opencode.implement.llm-context.v1",
        "ticket": ticket_text,
        "task": task_text,
        "approved_plan": plan_text,
        "required_hotspots": required_hotspots,
        "phase": str(state.get("Phase") or state.get("phase") or ""),
        "active_gate": str(state.get("active_gate") or ""),
        "next_gate_condition": str(state.get("next_gate_condition") or ""),
        "instruction": (
            "Apply concrete code edits in the repository for the approved plan. "
            "Do not only update .governance artifacts."
        ),
    }
    _write_text_atomic(context_file, json.dumps(context, ensure_ascii=True, indent=2) + "\n")

    final_cmd = executor_cmd
    if "{context_file}" in final_cmd:
        final_cmd = final_cmd.replace("{context_file}", shlex.quote(str(context_file)))

    result = subprocess.run(
        final_cmd,
        shell=True,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

    changed_files: list[str] = []
    try:
        probe = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            for raw in str(probe.stdout or "").splitlines():
                if len(raw) < 4:
                    continue
                changed_files.append(raw[3:].strip())
    except OSError:
        changed_files = []

    return {
        "ok": result.returncode == 0,
        "reason_code": "" if result.returncode == 0 else "IMPLEMENTATION-LLM-EXECUTOR-FAILED",
        "message": "" if result.returncode == 0 else str(result.stderr or result.stdout or "").strip(),
        "changed_files": changed_files,
        "llm_step_executed": True,
        "executor_command": executor_cmd,
        "executor_return_code": int(result.returncode),
    }


def _run_targeted_checks(repo_root: Path, requirements: list[dict[str, object]]) -> dict[str, object]:
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
        return {
            "ok": False,
            "reason_code": "IMPLEMENTATION-CHECKS-MISSING",
            "message": "No acceptance tests were defined in compiled requirements.",
            "executed": [],
            "failed": [],
        }

    command = ["python3", "-m", "pytest", "-q", *tests]
    result = subprocess.run(command, cwd=str(repo_root), capture_output=True, text=True, check=False)
    return {
        "ok": result.returncode == 0,
        "reason_code": "" if result.returncode == 0 else "IMPLEMENTATION-CHECKS-FAILED",
        "message": "" if result.returncode == 0 else str(result.stdout or result.stderr or "").strip(),
        "executed": tests,
        "failed": [] if result.returncode == 0 else tests,
        "return_code": int(result.returncode),
    }


def _diff_plan_coverage(
    *,
    repo_root: Path,
    domain_changes: list[str],
    replacements: list[tuple[str, str]],
) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    replacement_new = [new for _, new in replacements]
    for rel in domain_changes:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--", rel],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            body = str(result.stdout or "")
        else:
            path = repo_root / rel
            body = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        for token in replacement_new:
            if token and token in body:
                evidence.append(f"{rel}:{token}")
    return (len(evidence) > 0, evidence)


def _write_execution_code_artifact(repo_root: Path, plan_text: str, work_queue: list[str]) -> tuple[Path, bool]:
    out_dir = repo_root / ".governance" / "implementation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "execution_patch.py"
    digest = hashlib.sha256(plan_text.encode("utf-8")).hexdigest()[:12]
    queue_preview = "\\n".join(f"# - {item}" for item in work_queue[:5])
    content = (
        '"""Generated implementation execution artifact.\\n\\n'
        "This file is generated by /implement to start repository-side implementation work.\\n"
        '"""\\n\\n'
        f"PLAN_DIGEST = \"{digest}\"\\n"
        "\\n"
        "def execute_approved_plan() -> list[str]:\\n"
        "    \"\"\"Return the first execution tasks derived from approved plan.\"\"\"\\n"
        "    return [\\n"
        + "".join(f"        {item!r},\\n" for item in work_queue[:10])
        + "    ]\\n"
        "\\n"
        f"{queue_preview}\\n"
    )
    before = out_file.read_text(encoding="utf-8", errors="ignore") if out_file.exists() else None
    _write_text_atomic(out_file, content)
    after = out_file.read_text(encoding="utf-8", errors="ignore")
    return out_file, before != after


def _apply_target_file_patch(
    repo_root: Path,
    target: Path,
    *,
    note: str,
    replacements: list[tuple[str, str]],
) -> tuple[bool, bool]:
    suffix = target.suffix.lower()
    if suffix in {".py", ".sh", ".rb", ".pl"}:
        patch_line = f"\n# governance-implement: {note}\n"
    elif suffix in {".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h"}:
        patch_line = f"\n// governance-implement: {note}\n"
    else:
        patch_line = f"\n# governance-implement: {note}\n"
    text = target.read_text(encoding="utf-8", errors="ignore")
    updated = text
    semantic_changed = False
    for old, new in replacements:
        if old in updated:
            updated = updated.replace(old, new)
            semantic_changed = True
    if semantic_changed:
        _write_text_atomic(target, updated)
        return updated != text, True

    if "governance-implement:" in text:
        return False, False
    updated = text.rstrip("\n") + patch_line
    _write_text_atomic(target, updated)
    return updated != text, False


def _hash_files(paths: list[Path], repo_root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p)):
        rel = str(Path(os.path.abspath(str(path))).relative_to(repo_root))
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def _review_iteration(
    *,
    plan_text: str,
    changed_files: list[Path],
    repo_root: Path,
    required_hotspots: list[str],
    semantic_changed_files: list[str],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not changed_files:
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-NO-CHANGES",
                "message": "No repository files were changed by /implement execution.",
            }
        )
        return findings

    domain_changes = _domain_changed_files(changed_files, repo_root)
    if not domain_changes:
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-NON_DOMAIN-CHANGES",
                "message": "Implementation changed only governance artifacts and no repo domain files.",
            }
        )
    if required_hotspots and not any(rel in set(required_hotspots) for rel in domain_changes):
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-HOTSPOT-MISMATCH",
                "message": "No changed files match required code_hotspots from compiled requirements.",
            }
        )
    if domain_changes and not semantic_changed_files:
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-NO-SEMANTIC-MUTATION",
                "message": "Domain files changed, but no plan-derived semantic replacement was applied.",
            }
        )
    if domain_changes:
        status_visible: list[bool] = []
        status_unknown = False
        for rel in domain_changes:
            visible = _git_path_visible_in_status(repo_root, rel)
            if visible is None:
                status_unknown = True
                break
            status_visible.append(visible)
        if not status_unknown and not any(status_visible):
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": "IMPLEMENTATION-NOT-VISIBLE-IN-GIT-STATUS",
                    "message": "Implementation changes are not visible via git status for domain files.",
                }
            )

    for path in changed_files:
        rel = str(Path(os.path.abspath(str(path))).relative_to(repo_root))
        body = path.read_text(encoding="utf-8", errors="ignore")
        if not body.strip():
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": "IMPLEMENTATION-EMPTY-ARTIFACT",
                    "message": f"Changed file '{rel}' is empty.",
                }
            )

    artifact = next((p for p in changed_files if p.name == "execution_patch.py"), None)
    if artifact is not None:
        content = artifact.read_text(encoding="utf-8", errors="ignore")
        if "def execute_approved_plan" not in content:
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": "IMPLEMENTATION-MISSING-EXECUTE-FN",
                    "message": "execution_patch.py is missing execute_approved_plan().",
                }
            )
    if "[[force-implementation-blocker]]" in plan_text.lower():
        findings.append(
            {
                "severity": "critical",
                "reason_code": "IMPLEMENTATION-FORCED-BLOCKER",
                "message": "Forced blocker marker present in approved plan.",
            }
        )
    return findings


def _apply_iteration_revision(
    *,
    findings: list[dict[str, str]],
    changed_files: list[Path],
    repo_root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    fixed: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []
    artifact = next((p for p in changed_files if p.name == "execution_patch.py"), None)

    for finding in findings:
        code = finding.get("reason_code", "")
        if code == "IMPLEMENTATION-MISSING-EXECUTE-FN" and artifact is not None:
            text = artifact.read_text(encoding="utf-8", errors="ignore")
            text = text.rstrip("\n") + (
                "\n\ndef execute_approved_plan() -> list[str]:\n"
                "    \"\"\"Auto-repaired execute function.\"\"\"\n"
                "    return [\"apply approved implementation step\"]\n"
            )
            _write_text_atomic(artifact, text)
            fixed.append(finding)
            continue
        remaining.append(finding)
    return fixed, remaining


def _serialize_finding(finding: Mapping[str, str]) -> str:
    sev = str(finding.get("severity") or "unknown")
    code = str(finding.get("reason_code") or "UNKNOWN")
    msg = str(finding.get("message") or "")
    return f"{sev}:{code}:{msg}"


def _resolve_active_session_path() -> tuple[Path, Path]:
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="user")
    if evidence.config_root is None or evidence.workspaces_home is None:
        raise RuntimeError("binding unavailable")

    pointer_path = evidence.config_root / "SESSION_STATE.json"
    pointer = _load_json(pointer_path)
    fingerprint = str(pointer.get("activeRepoFingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("activeRepoFingerprint missing")

    active_state = str(pointer.get("activeSessionStateFile") or "").strip()
    if active_state:
        session_path = Path(active_state)
    else:
        session_path = evidence.workspaces_home / fingerprint / "SESSION_STATE.json"

    if not session_path.is_absolute():
        raise RuntimeError("activeSessionStateFile must be absolute")
    if not session_path.exists():
        raise RuntimeError("active session missing")

    events_path = session_path.parent / "events.jsonl"
    return session_path, events_path


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

    phase_text = str(state.get("Phase") or state.get("phase") or "").strip()
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

    active_gate = str(state.get("active_gate") or "").strip().lower()
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
    plan_record_file = session_path.parent / "plan-record.json"
    plan_text = _latest_plan_text(plan_record_file)

    repo_root = _repo_root(session_path, state)
    compiled_requirements = _load_compiled_requirements(session_path, state)
    contract_titles = [str(req.get("title") or "").strip() for req in compiled_requirements if isinstance(req, dict)]
    work_queue = _build_execution_work_queue(plan_text, state, contract_titles)
    required_hotspot_files = _extract_hotspot_files(compiled_requirements, repo_root)
    required_hotspots_rel = [str(path.relative_to(repo_root)) for path in required_hotspot_files]
    replacements = _extract_literal_replacements(
        "\n".join([str(state.get("Ticket") or ""), str(state.get("Task") or ""), plan_text])
    )

    llm_result = _run_llm_edit_step(
        repo_root=repo_root,
        state=state,
        ticket_text=str(state.get("Ticket") or ""),
        task_text=str(state.get("Task") or ""),
        plan_text=plan_text,
        required_hotspots=required_hotspots_rel,
    )
    if not bool(llm_result.get("ok")):
        return _payload(
            "blocked",
            reason_code=str(llm_result.get("reason_code") or "IMPLEMENTATION-LLM-EXECUTOR-FAILED"),
            message=str(llm_result.get("message") or "LLM implementation executor failed."),
            phase="6-PostFlight",
            next="6",
            active_gate="Implementation Blocked",
            next_gate_condition="Implementation blocked before review loop; LLM edit step failed.",
        )

    changed_files: list[Path] = []
    semantic_changed_files: list[str] = []
    execution_artifact, execution_artifact_changed = _write_execution_code_artifact(repo_root, plan_text, work_queue)
    if execution_artifact_changed:
        changed_files.append(execution_artifact)
    target_candidates = required_hotspot_files or _extract_candidate_files(
        "\n".join([str(state.get("Ticket") or ""), str(state.get("Task") or ""), plan_text]),
        repo_root,
    )
    for candidate in target_candidates:
        changed, semantic_changed = _apply_target_file_patch(
            repo_root,
            candidate,
            note="approved-plan execution touched this file",
            replacements=replacements,
        )
        if changed:
            changed_files.append(candidate)
            if semantic_changed:
                semantic_changed_files.append(str(candidate.relative_to(repo_root)))

    checks_result = _run_targeted_checks(repo_root, compiled_requirements)
    checks_ok = bool(checks_result.get("ok"))

    max_iterations = 3
    min_iterations = 1
    iteration = 0
    previous_digest = ""
    revision_delta = "changed"
    open_findings: list[dict[str, str]] = []
    fixed_findings: list[dict[str, str]] = []
    loop_notes: list[str] = []
    quality_stable = False
    stage_history: list[str] = ["Implementation Execution In Progress"]
    coverage_evidence_latest: list[str] = []

    while iteration < max_iterations:
        iteration += 1
        current_digest = _hash_files(changed_files, repo_root)
        stage_history.append("Implementation Self Review")
        findings = _review_iteration(
            plan_text=plan_text,
            changed_files=changed_files,
            repo_root=repo_root,
            required_hotspots=required_hotspots_rel,
            semantic_changed_files=semantic_changed_files,
        )
        if not checks_ok:
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": str(checks_result.get("reason_code") or "IMPLEMENTATION-CHECKS-FAILED"),
                    "message": str(checks_result.get("message") or "Targeted implementation checks failed."),
                }
            )
        domain_changes = _domain_changed_files(changed_files, repo_root)
        plan_covered, coverage_evidence = _diff_plan_coverage(
            repo_root=repo_root,
            domain_changes=domain_changes,
            replacements=replacements,
        )
        coverage_evidence_latest = coverage_evidence
        if not plan_covered:
            findings.append(
                {
                    "severity": "critical",
                    "reason_code": "IMPLEMENTATION-PLAN-COVERAGE-MISSING",
                    "message": "No plan-derived coverage evidence found in real repository diffs.",
                }
            )
        critical = [f for f in findings if str(f.get("severity")) == "critical"]
        if critical:
            stage_history.append("Implementation Revision")
            fixed, remaining = _apply_iteration_revision(
                findings=critical,
                changed_files=changed_files,
                repo_root=repo_root,
            )
            fixed_findings.extend(fixed)
            open_findings = remaining
            revision_delta = "changed" if fixed else "max-reached-with-open-delta"
            loop_notes.append(
                f"iteration={iteration}: critical_findings={len(critical)}, fixed={len(fixed)}, remaining={len(remaining)}"
            )
            if remaining and iteration >= max_iterations:
                break
            previous_digest = current_digest
            continue

        stage_history.append("Implementation Verification")
        if previous_digest and previous_digest == current_digest and iteration >= min_iterations:
            quality_stable = True
            revision_delta = "stabilized"
            open_findings = []
            loop_notes.append(f"iteration={iteration}: stable digest reached")
            break

        if iteration >= min_iterations and not findings:
            quality_stable = True
            revision_delta = "no-change" if previous_digest == current_digest else "stabilized"
            open_findings = []
            loop_notes.append(f"iteration={iteration}: no open findings")
            break

        previous_digest = current_digest

    if not quality_stable and not open_findings and iteration >= max_iterations:
        revision_delta = "max-reached-with-open-delta"

    changed_rel = [str(Path(os.path.abspath(str(p))).relative_to(repo_root)) for p in changed_files]
    checks_executed_raw = checks_result.get("executed")
    checks_executed = [str(item) for item in checks_executed_raw] if isinstance(checks_executed_raw, list) else []
    fixed_serialized = [_serialize_finding(f) for f in fixed_findings]
    open_serialized = [_serialize_finding(f) for f in open_findings]
    hard_reason_code = ""
    if open_serialized:
        parts = str(open_serialized[0]).split(":", 2)
        if len(parts) >= 2:
            hard_reason_code = parts[1].strip()
    if not hard_reason_code:
        hard_reason_code = "IMPLEMENTATION-HARD-BLOCKER"

    state["implementation_authorized"] = True
    state["implementation_started"] = True
    state["implementation_status"] = "in_progress" if quality_stable else "blocked"
    state["implementation_started_at"] = ts
    state["implementation_started_by"] = actor.strip() or "operator"
    state["implementation_start_note"] = note.strip()
    state["implementation_handoff_plan_record_versions"] = signal.versions
    state["Next"] = "6"
    state["next"] = "6"
    state["implementation_execution_started"] = True
    state["implementation_execution_status"] = "review_complete" if quality_stable else "blocked"
    state["implementation_execution_summary"] = (
        "Implementation execution completed with internal review loop."
        if quality_stable
        else "Implementation execution blocked: unresolved critical findings remain."
    )
    state["implementation_artifacts_expected"] = ["source changes", "tests", "review evidence"]
    state["implementation_work_queue"] = work_queue
    state["implementation_current_step"] = work_queue[0] if work_queue else "none"
    state["implementation_changed_files"] = changed_rel
    state["implementation_semantic_changed_files"] = semantic_changed_files
    state["implementation_required_hotspots"] = required_hotspots_rel
    state["implementation_llm_step_executed"] = bool(llm_result.get("llm_step_executed"))
    state["implementation_llm_executor_command"] = str(llm_result.get("executor_command") or "")
    state["implementation_checks_executed"] = checks_executed
    state["implementation_checks_ok"] = checks_ok
    state["implementation_plan_coverage_evidence"] = coverage_evidence_latest
    state["execution_receipt"] = {
        "receipt_type": "execution_receipt",
        "requirement_scope": "R-IMPLEMENT-001",
        "content_digest": hashlib.sha256("|".join(changed_rel).encode("utf-8")).hexdigest(),
        "rendered_at": ts,
        "render_event_id": event_id,
        "gate": str(state.get("active_gate") or "Implementation Execution In Progress"),
        "session_id": str(state.get("session_run_id") or "unknown-session"),
        "state_revision": str(state.get("session_materialization_event_id") or event_id),
        "source_command": "/implement",
        "changed_files": changed_rel,
        "checks_started": ["internal implementation self-review loop", "artifact integrity check"],
        "checks_executed": checks_executed,
        "blocked_reason_code": hard_reason_code if not quality_stable else "none",
    }
    state["implementation_review_iterations"] = iteration
    state["implementation_max_review_iterations"] = max_iterations
    state["implementation_min_review_iterations"] = min_iterations
    state["implementation_revision_delta"] = revision_delta
    state["implementation_quality_stable"] = quality_stable
    state["implementation_findings_fixed"] = fixed_serialized
    state["implementation_open_findings"] = open_serialized
    state["implementation_loop_notes"] = loop_notes
    state["implementation_hard_blockers"] = open_serialized
    state["implementation_substate_history"] = stage_history

    if quality_stable:
        state["active_gate"] = "Implementation Review Complete"
        state["next_gate_condition"] = (
            "Internal implementation review loop is complete. "
            "Run /continue to materialize the Implementation Presentation Gate."
        )
        state["implementation_review_complete_state"] = True
        state["implementation_package_presented"] = True
        state["implementation_package_review_object"] = "Implemented result review"
        state["implementation_package_plan_reference"] = "latest approved plan record"
        state["implementation_package_changed_files"] = changed_rel
        state["implementation_package_findings_fixed"] = fixed_serialized
        state["implementation_package_findings_open"] = open_serialized
        state["implementation_package_checks"] = [
            "internal implementation self-review loop",
            "artifact integrity check",
            "plan-conformance heuristic",
        ]
        state["implementation_package_stability"] = "stable"
        stage_history.append("Implementation Review Complete")
    else:
        state["active_gate"] = "Implementation Blocked"
        state["next_gate_condition"] = (
            "Implementation blocked by unresolved critical findings. "
            f"reason_code={hard_reason_code}. Resolve blockers and rerun /implement."
        )
        state["implementation_package_presented"] = False

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.implementation-started.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "IMPLEMENTATION_STARTED",
        "phase": phase_text,
        "active_gate": str(state.get("active_gate") or "Implementation Blocked"),
        "decision": decision or "approve",
        "plan_record_versions": signal.versions,
        "actor": state["implementation_started_by"],
        "note": state["implementation_start_note"],
        "execution_status": "in_progress",
        "work_queue_items": len(work_queue),
        "current_step": state["implementation_current_step"],
        "review_iterations": iteration,
        "review_max_iterations": max_iterations,
        "revision_delta": revision_delta,
        "quality_stable": quality_stable,
        "changed_files": changed_rel,
        "open_findings": open_serialized,
    }
    if events_path is not None:
        _append_event(events_path, audit_event)

    payload = _payload(
        "ok" if quality_stable else "blocked",
        event_id=event_id,
        phase="6-PostFlight",
        next="6",
        active_gate=str(state.get("active_gate") or "Implementation Blocked"),
        next_gate_condition=state["next_gate_condition"],
        implementation_authorized=True,
        implementation_started=True,
        implementation_started_at=ts,
        implementation_execution_started=True,
        implementation_execution_status=state["implementation_execution_status"],
        implementation_execution_summary=state["implementation_execution_summary"],
        implementation_artifacts_expected=state["implementation_artifacts_expected"],
        implementation_blockers=open_serialized,
        implementation_work_queue=work_queue,
        implementation_current_step=state["implementation_current_step"],
        implementation_required_hotspots=required_hotspots_rel,
        implementation_changed_files=changed_rel,
        implementation_semantic_changed_files=semantic_changed_files,
        implementation_llm_step_executed=bool(llm_result.get("llm_step_executed")),
        implementation_checks_executed=checks_executed,
        implementation_checks_ok=checks_ok,
        implementation_plan_coverage_evidence=coverage_evidence_latest,
        implementation_review_iterations=iteration,
        implementation_max_review_iterations=max_iterations,
        implementation_revision_delta=revision_delta,
        implementation_substate_history=stage_history,
        implementation_findings_fixed=fixed_serialized,
        implementation_open_findings=open_serialized,
        implementation_quality_stable=quality_stable,
        next_action=(
            "run /continue."
            if quality_stable
            else "resolve implementation blockers, then run /implement."
        ),
    )
    if not quality_stable:
        payload["reason_code"] = hard_reason_code
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
