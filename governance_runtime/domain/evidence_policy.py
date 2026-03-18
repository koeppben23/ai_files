from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Final, Mapping


EVIDENCE_CLASS_DEFAULT_TTL_SECONDS: dict[str, int] = {
    "identity_signal": 0,
    "preflight_probe": 0,
    "gate_evidence": 24 * 60 * 60,
    "runtime_diagnostic": 24 * 60 * 60,
    "operator_provided": 24 * 60 * 60,
}


# ---------------------------------------------------------------------------
# Artifact-kind → freshness class mapping
# ---------------------------------------------------------------------------
# Maps logical artifact kinds (used in YAML ``pass_criteria.artifact_kind``)
# to the evidence_class that governs their TTL.  This keeps evidence_policy.py
# as the single source of truth for freshness rules while YAML contracts only
# declare *which* artifacts are required.
ARTIFACT_KIND_FRESHNESS_CLASS: Final[dict[str, str]] = {
    # Identity / preflight — zero-TTL (must be live)
    "repo_identity": "identity_signal",
    "model_identity": "identity_signal",
    "preflight_signal": "preflight_probe",
    # Gate artefacts — 24 h TTL
    "test_quality_gate": "gate_evidence",
    "business_rules_gate": "gate_evidence",
    "rollback_safety_gate": "gate_evidence",
    "risk_tier_assessment": "gate_evidence",
    "scorecard_calibration": "gate_evidence",
    "principal_quality_claims": "gate_evidence",
    # Runtime diagnostics — 24 h TTL
    "runtime_log": "runtime_diagnostic",
    "runtime_metrics": "runtime_diagnostic",
    # Operator-supplied overrides — 24 h TTL
    "operator_override": "operator_provided",
    "manual_attestation": "operator_provided",
}


def resolve_freshness_class(artifact_kind: str) -> str:
    """Return the evidence_class governing *artifact_kind*'s TTL.

    Falls back to ``"gate_evidence"`` for unknown artifact kinds so that
    callers always get a valid class with a sensible default TTL.
    """
    return ARTIFACT_KIND_FRESHNESS_CLASS.get(
        artifact_kind.strip().lower(), "gate_evidence"
    )


def canonical_claim_evidence_id(claim: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", claim.strip().lower()).strip("-")
    if not normalized:
        return ""
    return f"claim/{normalized}"


def parse_observed_at(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_ttl_seconds(item: Mapping[str, object]) -> int:
    ttl_raw = item.get("ttl_seconds")
    if isinstance(ttl_raw, int) and ttl_raw >= 0:
        return ttl_raw
    evidence_class = str(item.get("evidence_class", "gate_evidence")).strip().lower()
    return EVIDENCE_CLASS_DEFAULT_TTL_SECONDS.get(evidence_class, 24 * 60 * 60)


def is_stale(*, observed_at: datetime | None, ttl_seconds: int, now_utc: datetime) -> bool:
    if observed_at is None:
        return True
    if ttl_seconds == 0:
        return now_utc - observed_at > timedelta(seconds=1)
    return now_utc - observed_at > timedelta(seconds=ttl_seconds)


def extract_verified_claim_evidence_ids(
    session_state_document: Mapping[str, object] | None,
    *,
    now_utc: datetime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if session_state_document is None:
        return (), ()

    root: Mapping[str, object]
    session_state = session_state_document.get("SESSION_STATE")
    if isinstance(session_state, Mapping):
        root = session_state
    else:
        root = session_state_document

    build_evidence = root.get("BuildEvidence")
    if not isinstance(build_evidence, Mapping):
        return (), ()

    observed: set[str] = set()
    stale: set[str] = set()

    claims_stale = build_evidence.get("claims_stale")
    if isinstance(claims_stale, list):
        for entry in claims_stale:
            if isinstance(entry, str) and entry.strip():
                stale.add(entry.strip())

    items = build_evidence.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            result = str(item.get("result", "")).strip().lower()
            verified = item.get("verified") is True
            if result not in {"pass", "passed", "ok", "success"} and not verified:
                continue

            evidence_id = item.get("evidence_id")
            candidate_id = ""
            if isinstance(evidence_id, str) and evidence_id.strip():
                candidate_id = evidence_id.strip()
            else:
                claim_id = item.get("claim_id")
                if isinstance(claim_id, str) and claim_id.strip():
                    candidate_id = claim_id.strip()
                else:
                    claim_label = item.get("claim")
                    if isinstance(claim_label, str) and claim_label.strip():
                        candidate_id = canonical_claim_evidence_id(claim_label)

            if not candidate_id:
                continue

            observed_at = parse_observed_at(item.get("observed_at"))
            ttl_seconds = resolve_ttl_seconds(item)
            if is_stale(observed_at=observed_at, ttl_seconds=ttl_seconds, now_utc=now_utc):
                stale.add(candidate_id)
            else:
                observed.add(candidate_id)

    stale -= observed
    return tuple(sorted(observed)), tuple(sorted(stale))
