"""Run one governance quality benchmark pack deterministically.

Exit codes:
- 0: pass
- 2: not_verified (missing/stale required evidence)
- 3: fail (scored below pass threshold)
- 4: blocked (invalid input)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


EXIT_PASS = 0
EXIT_NOT_VERIFIED = 2
EXIT_FAIL = 3
EXIT_BLOCKED = 4


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _parse_claim_list(values: list[str]) -> set[str]:
    result: set[str] = set()
    for raw in values:
        value = raw.strip()
        if value:
            result.add(value)
    return result


def _parse_criterion_scores(values: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"invalid --criterion-score '{raw}', expected CRITERION_ID=value")
        criterion_id, value_str = raw.split("=", 1)
        cid = criterion_id.strip()
        if not cid:
            raise ValueError(f"invalid --criterion-score '{raw}', empty criterion id")
        try:
            value = float(value_str.strip())
        except ValueError as exc:
            raise ValueError(f"invalid score for {cid}: {value_str!r}") from exc
        if value < 0 or value > 1:
            raise ValueError(f"score for {cid} must be in [0,1], got {value}")
        scores[cid] = value
    return scores


def _derive_observed_claims_from_evidence_dir(evidence_dir: Path) -> set[str]:
    required = ("pytest.exitcode", "governance_lint.exitcode", "drift.txt")
    missing = [name for name in required if not (evidence_dir / name).exists()]
    if missing:
        raise ValueError(f"evidence dir missing required files: {', '.join(missing)}")

    observed: set[str] = set()
    if (evidence_dir / "pytest.exitcode").read_text(encoding="utf-8").strip() == "0":
        observed.add("claim/tests-green")
    if (evidence_dir / "governance_lint.exitcode").read_text(encoding="utf-8").strip() == "0":
        observed.add("claim/static-clean")
    if not (evidence_dir / "drift.txt").read_text(encoding="utf-8").strip():
        observed.add("claim/no-drift")
    return observed


def run_benchmark(
    *,
    pack: dict[str, Any],
    observed_claim_ids: set[str],
    stale_claim_ids: set[str],
    criterion_scores: dict[str, float],
) -> tuple[int, dict[str, Any]]:
    tasks = pack.get("tasks")
    rubric = pack.get("rubric")
    if not isinstance(tasks, list) or not isinstance(rubric, dict):
        raise ValueError("benchmark pack must contain 'tasks' list and 'rubric' object")

    required_claims: set[str] = set()
    task_results: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id", "unknown")).strip() or "unknown"
        req = task.get("required_evidence_claim_ids")
        required_for_task = set(req) if isinstance(req, list) else set()
        required_for_task = {str(x).strip() for x in required_for_task if str(x).strip()}
        required_claims.update(required_for_task)

        missing = sorted(required_for_task - observed_claim_ids)
        stale = sorted(required_for_task.intersection(stale_claim_ids))
        status = "NOT_VERIFIED" if missing or stale else "VERIFIED"
        task_results.append(
            {
                "id": task_id,
                "status": status,
                "missing_required_claim_ids": missing,
                "stale_required_claim_ids": stale,
            }
        )

    missing_required = sorted(required_claims - observed_claim_ids)
    stale_required = sorted(required_claims.intersection(stale_claim_ids))

    criteria = rubric.get("criteria")
    thresholds = rubric.get("thresholds")
    if not isinstance(criteria, list) or not isinstance(thresholds, dict):
        raise ValueError("rubric must contain 'criteria' list and 'thresholds' object")

    weighted_total = 0.0
    weighted_possible = 0.0
    per_criterion: list[dict[str, Any]] = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        cid = str(criterion.get("id", "")).strip()
        if not cid:
            continue
        weight_raw = criterion.get("weight", 0)
        if not isinstance(weight_raw, (int, float)):
            raise ValueError(f"criterion {cid} has non-numeric weight")
        weight = float(weight_raw)
        if weight < 0:
            raise ValueError(f"criterion {cid} has negative weight")
        score = criterion_scores.get(cid, 0.0)
        weighted_total += score * weight
        weighted_possible += weight
        per_criterion.append({"id": cid, "weight": weight, "score": score})

    ratio = (weighted_total / weighted_possible) if weighted_possible else 0.0
    pass_ratio = float(thresholds.get("pass_ratio", 0.85))
    high_conf_ratio = float(thresholds.get("high_confidence_ratio", 0.9))

    status = "PASS"
    exit_code = EXIT_PASS
    if missing_required or stale_required:
        status = "NOT_VERIFIED"
        exit_code = EXIT_NOT_VERIFIED
    elif ratio < pass_ratio:
        status = "FAIL"
        exit_code = EXIT_FAIL

    confidence = "HIGH" if ratio >= high_conf_ratio else ("MEDIUM" if ratio >= pass_ratio else "LOW")
    result = {
        "schema": "governance-quality-benchmark-result.v1",
        "pack_profile": str(pack.get("profile", "unknown")),
        "status": status,
        "confidence": confidence,
        "score_ratio": round(ratio, 6),
        "thresholds": {
            "pass_ratio": pass_ratio,
            "high_confidence_ratio": high_conf_ratio,
        },
        "required_claim_ids": sorted(required_claims),
        "missing_required_claim_ids": missing_required,
        "stale_required_claim_ids": stale_required,
        "criterion_scores": per_criterion,
        "tasks": task_results,
    }
    return exit_code, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic governance quality benchmark pack.")
    parser.add_argument("--pack", required=True, help="Path to benchmark pack JSON.")
    parser.add_argument(
        "--observed-claim",
        action="append",
        default=[],
        help="Observed claim evidence id (repeatable).",
    )
    parser.add_argument(
        "--stale-claim",
        action="append",
        default=[],
        help="Stale claim evidence id (repeatable).",
    )
    parser.add_argument(
        "--criterion-score",
        action="append",
        default=[],
        help="Criterion score as CRITERION_ID=value in [0,1] (repeatable).",
    )
    parser.add_argument(
        "--evidence-dir",
        default="",
        help="Optional evidence directory with pytest.exitcode/governance_lint.exitcode/drift.txt.",
    )
    parser.add_argument(
        "--review-mode",
        action="store_true",
        help="Require evidence-only claim derivation (no --observed-claim injection).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional result output file path. If omitted, prints to stdout only.",
    )

    args = parser.parse_args(argv)

    try:
        pack = _load_json(Path(args.pack))
        evidence_dir = Path(args.evidence_dir) if args.evidence_dir else None
        if args.review_mode and evidence_dir is None:
            raise ValueError("--review-mode requires --evidence-dir")
        if evidence_dir is not None and args.observed_claim:
            raise ValueError("--evidence-dir cannot be combined with --observed-claim")

        observed_claims: set[str]
        if evidence_dir is not None:
            observed_claims = _derive_observed_claims_from_evidence_dir(evidence_dir)
        else:
            observed_claims = _parse_claim_list(args.observed_claim)

        stale_claims = _parse_claim_list(args.stale_claim)
        criterion_scores = _parse_criterion_scores(args.criterion_score)
        code, result = run_benchmark(
            pack=pack,
            observed_claim_ids=observed_claims,
            stale_claim_ids=stale_claims,
            criterion_scores=criterion_scores,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "schema": "governance-quality-benchmark-result.v1",
                    "status": "BLOCKED",
                    "message": str(exc),
                },
                ensure_ascii=True,
            )
        )
        return EXIT_BLOCKED

    encoded = json.dumps(result, ensure_ascii=True)
    print(encoded)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
