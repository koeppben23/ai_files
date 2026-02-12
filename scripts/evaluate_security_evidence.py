#!/usr/bin/env python3
"""Aggregate scanner evidence and enforce deterministic security gate policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


POLICY_SCHEMA = "governance.security-gate-policy.v1"
SUMMARY_SCHEMA = "governance.security-evidence-summary.v1"
SEVERITIES = ("critical", "high", "medium", "low", "unknown")


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _normalize_findings_map(raw: object, *, scanner: str) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError(f"scanner {scanner}: findings_by_severity must be an object")
    out: dict[str, int] = {name: 0 for name in SEVERITIES}
    for key, val in raw.items():
        norm_key = str(key).strip().lower()
        if norm_key not in out:
            continue
        try:
            out[norm_key] = int(val)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"scanner {scanner}: findings_by_severity[{key}] is not an integer") from exc
    return out


def _load_policy(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    if payload.get("schema") != POLICY_SCHEMA:
        raise ValueError(f"{path}: expected schema {POLICY_SCHEMA}")
    raw_block = payload.get("block_on_severities")
    if not isinstance(raw_block, list) or not raw_block:
        raise ValueError(f"{path}: block_on_severities must be a non-empty list")
    normalized_block = []
    for item in raw_block:
        sev = str(item).strip().lower()
        if sev not in SEVERITIES:
            raise ValueError(f"{path}: unsupported severity in block_on_severities: {item}")
        normalized_block.append(sev)
    payload["block_on_severities"] = sorted(dict.fromkeys(normalized_block))
    payload["fail_closed_on_scanner_error"] = bool(payload.get("fail_closed_on_scanner_error", True))
    return payload


def _load_scanner_summary(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    scanner = str(payload.get("scanner_id", "")).strip()
    if not scanner:
        raise ValueError(f"{path}: scanner_id is required")
    status = str(payload.get("status", "")).strip().lower()
    if status not in {"success", "failure", "partial"}:
        raise ValueError(f"{path}: status must be success|failure|partial")

    findings = _normalize_findings_map(payload.get("findings_by_severity"), scanner=scanner)
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ValueError(f"{path}: notes must be a string when provided")

    evidence_paths = payload.get("evidence_paths", [])
    if evidence_paths is None:
        evidence_paths = []
    if not isinstance(evidence_paths, list):
        raise ValueError(f"{path}: evidence_paths must be an array")

    return {
        "scanner_id": scanner,
        "status": status,
        "findings_by_severity": findings,
        "notes": notes or "",
        "evidence_paths": [str(item) for item in evidence_paths],
    }


def evaluate(*, policy: dict[str, object], scanner_summaries: list[dict[str, object]]) -> tuple[int, dict[str, object]]:
    totals = {name: 0 for name in SEVERITIES}
    blocked_reasons: list[str] = []

    block_on = [str(item) for item in policy["block_on_severities"]]
    fail_closed = bool(policy["fail_closed_on_scanner_error"])

    for summary in scanner_summaries:
        findings = summary["findings_by_severity"]
        for sev in SEVERITIES:
            totals[sev] += int(findings[sev])

        status = str(summary["status"])
        if fail_closed and status != "success":
            blocked_reasons.append(
                f"BLOCKED-SCANNER-STATUS: {summary['scanner_id']} reported status={status}"
            )

    for sev in block_on:
        count = totals.get(sev, 0)
        if count and count > 0:
            blocked_reasons.append(
                f"BLOCKED-SECURITY-SEVERITY: {sev} findings count={count} exceeds policy"
            )

    blocked = bool(blocked_reasons)
    output = {
        "schema": SUMMARY_SCHEMA,
        "policy_schema": POLICY_SCHEMA,
        "session_state_evidence_key": policy.get("session_state_evidence_key", "SESSION_STATE.BuildEvidence.Security"),
        "block_on_severities": block_on,
        "fail_closed_on_scanner_error": fail_closed,
        "scanners": scanner_summaries,
        "totals_by_severity": totals,
        "blocked": blocked,
        "blocked_reasons": blocked_reasons,
        "status": "BLOCKED" if blocked else "OK",
    }
    return (1 if blocked else 0, output)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate security scanner summaries against deterministic policy.")
    parser.add_argument("--policy", default="diagnostics/SECURITY_GATE_POLICY.json")
    parser.add_argument("--input", action="append", required=True, help="Path to scanner summary JSON (repeatable).")
    parser.add_argument("--output", required=True, help="Path to write aggregated security summary JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        policy = _load_policy(Path(args.policy))
        scanner_summaries = [_load_scanner_summary(Path(path)) for path in args.input]
        code, output = evaluate(policy=policy, scanner_summaries=scanner_summaries)
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "message": str(exc)}, ensure_ascii=True))
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
